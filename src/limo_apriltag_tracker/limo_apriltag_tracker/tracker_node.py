#!/usr/bin/env python3
import time
import math
import cv2
import numpy as np
import threading

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo, JointState
from geometry_msgs.msg import Twist
from cv_bridge import CvBridge, CvBridgeError

try:
    from pupil_apriltags import Detector
except ImportError:
    Detector = None


class AprilTagTrackerNode(Node):
    def __init__(self):
        super().__init__('apriltag_tracker_node')

        # Check dependency
        if Detector is None:
            self.get_logger().error(
                "pupil-apriltags is not installed or failed to import! "
                "Please make sure pupil-apriltags is installed."
            )
            raise RuntimeError("Missing pupil-apriltags dependency")

        # States: TRACKING, PICKING, DONE
        self.state = 'TRACKING'
        self.tracking_stable_start_time = None

        # Declare ROS 2 parameters
        self.declare_parameter('tag_family', 'tag36h11')
        self.declare_parameter('tag_size', 0.12)  # Size of AprilTag in meters
        self.declare_parameter('target_distance', 0.45)  # Target distance in meters
        self.declare_parameter('distance_tolerance', 0.05)  # Distance deadband in meters
        self.declare_parameter('centering_pixel_tolerance', 20)  # Centering deadband in pixels
        self.declare_parameter('target_tag_id', -1)  # -1 means track any detected tag
        self.declare_parameter('linear_kp', 0.6)
        self.declare_parameter('angular_kp', 0.0025)
        self.declare_parameter('max_linear_speed', 0.12)  # m/s
        self.declare_parameter('max_angular_speed', 0.4)  # rad/s

        # Retrieve parameters
        self.tag_family = self.get_parameter('tag_family').value
        self.tag_size = self.get_parameter('tag_size').value
        self.target_distance = self.get_parameter('target_distance').value
        self.distance_tolerance = self.get_parameter('distance_tolerance').value
        self.centering_pixel_tolerance = self.get_parameter('centering_pixel_tolerance').value
        self.target_tag_id = self.get_parameter('target_tag_id').value
        self.linear_kp = self.get_parameter('linear_kp').value
        self.angular_kp = self.get_parameter('angular_kp').value
        self.max_linear_speed = self.get_parameter('max_linear_speed').value
        self.max_angular_speed = self.get_parameter('max_angular_speed').value

        # Initialize detector
        self.get_logger().info(f"Initializing AprilTag detector for family: {self.tag_family}")
        self.detector = Detector(
            families=self.tag_family,
            nthreads=2,
            quad_decimate=1.0,
            quad_sigma=0.0,
            refine_edges=1,
            decode_sharpening=0.25,
            debug=0
        )

        self.bridge = CvBridge()
        self.camera_params = None  # [fx, fy, cx, cy]
        self.last_tag_seen_time = 0.0
        self.safety_timeout = 0.6  # Stop robot if tag is lost for 0.6 seconds

        # Publishers
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.debug_img_pub = self.create_publisher(Image, '/apriltag_tracker/debug_image', 10)

        # myCobot Arm Publishers
        self.joint_pub = self.create_publisher(JointState, '/joint_states', 10)
        self.joint_msg = JointState()
        self.joint_msg.name = [
            'joint2_to_joint1', 'joint3_to_joint2', 'joint4_to_joint3',
            'joint5_to_joint4', 'joint6_to_joint5', 'joint6output_to_joint6',
            'gripper_controller', 'gripper_base_to_gripper_left2',
            'gripper_left3_to_gripper_left1', 'gripper_base_to_gripper_right3',
            'gripper_base_to_gripper_right2', 'gripper_right3_to_gripper_right1'
        ]
        self.arm_target_position = None
        self.arm_timer = self.create_timer(0.02, self.arm_timer_callback) # 50Hz

        # Subscriptions
        self.cam_info_sub = self.create_subscription(
            CameraInfo,
            '/camera/color/camera_info',
            self.camera_info_callback,
            10
        )
        self.image_sub = self.create_subscription(
            Image,
            '/camera/color/image_raw',
            self.image_callback,
            10
        )

        self.get_logger().info("AprilTag Tracker Node started and listening...")

    def arm_timer_callback(self):
        if self.arm_target_position is not None:
            self.joint_msg.header.stamp = self.get_clock().now().to_msg()
            self.joint_msg.position = self.arm_target_position
            self.joint_pub.publish(self.joint_msg)

    def set_arm_target(self, pos6, gripper_open):
        target = list(pos6)
        # Gripper values based on mission_ws.py standards
        if gripper_open:
            target.extend([0.15, 0.15, -0.15, -0.15, -0.15, 0.15])
        else:
            target.extend([-0.74, -0.74, 0.74, 0.74, 0.74, -0.74])
        self.arm_target_position = target

    def execute_pick_sequence(self):
        def sequence():
            # Ensure base is stopped before moving arm
            cmd = Twist()
            self.cmd_pub.publish(cmd)
            
            home_pose = [0.0] * 6
            pre_pick_pose = [
                -1.44200678, -0.69978976, -0.43876004,
                -0.29739344, -0.0003316, -0.66224717
            ]
            pick_pose = [
                -1.44200678, -1.06972052, -0.3822134,
                -0.12722994, -0.0003316, -0.66224717
            ]
            
            try:
                self.get_logger().info('--- Moving arm to HOME and OPENING gripper ---')
                self.set_arm_target(home_pose, gripper_open=True)
                time.sleep(4.0)
                
                self.get_logger().info('--- Moving arm to PRE-PICK (top-down) pose ---')
                self.set_arm_target(pre_pick_pose, gripper_open=True)
                time.sleep(5.0)
                
                self.get_logger().info('--- Moving arm down to PICK pose ---')
                self.set_arm_target(pick_pose, gripper_open=True)
                time.sleep(3.0)
                
                self.get_logger().info('--- CLOSING gripper to grasp cube ---')
                self.set_arm_target(pick_pose, gripper_open=False)
                time.sleep(4.0)
                
                self.get_logger().info('--- Lifting back to PRE-PICK ---')
                self.set_arm_target(pre_pick_pose, gripper_open=False)
                time.sleep(3.0)
                
                self.get_logger().info('--- Returning to HOME ---')
                self.set_arm_target(home_pose, gripper_open=False)
                time.sleep(4.0)
                
                self.get_logger().info('--- Pick sequence COMPLETE ---')
            except Exception as e:
                self.get_logger().error(f"Error during pick sequence: {e}")
            finally:
                self.state = 'DONE'

        threading.Thread(target=sequence, daemon=True).start()

    def camera_info_callback(self, msg):
        # Intrinsics: K = [fx, 0, cx, 0, fy, cy, 0, 0, 1]
        # We need [fx, fy, cx, cy]
        if self.camera_params is None:
            self.camera_params = [msg.k[0], msg.k[4], msg.k[2], msg.k[5]]
            self.get_logger().info(
                f"Received camera intrinsics: fx={msg.k[0]:.2f}, fy={msg.k[4]:.2f}, cx={msg.k[2]:.2f}, cy={msg.k[5]:.2f}"
            )

    def image_callback(self, msg):
        # Only process images and move base if we are in TRACKING state
        if self.state != 'TRACKING':
            # Stop the robot if we somehow receive images but shouldn't track
            if self.state == 'DONE':
                cmd = Twist()
                self.cmd_pub.publish(cmd)
            return

        try:
            # Convert ROS Image to OpenCV BGR
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except CvBridgeError as e:
            self.get_logger().error(f"Failed to convert image: {e}")
            return

        h, w, _ = cv_image.shape
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

        # Detect AprilTags
        estimate_pose = (self.camera_params is not None)
        if estimate_pose:
            detections = self.detector.detect(
                gray,
                estimate_tag_pose=True,
                camera_params=self.camera_params,
                tag_size=self.tag_size
            )
        else:
            detections = self.detector.detect(gray, estimate_tag_pose=False)

        selected_detection = None
        current_time = time.time()

        # Find the tag to track
        for det in detections:
            if self.target_tag_id == -1 or det.tag_id == self.target_tag_id:
                selected_detection = det
                break

        cmd = Twist()

        if selected_detection is not None:
            self.last_tag_seen_time = current_time
            corners = selected_detection.corners
            center = selected_detection.center
            tag_id = selected_detection.tag_id

            # Calculate errors
            center_x = center[0]
            err_x = center_x - (w / 2.0)

            # Estimate distance
            if estimate_pose and selected_detection.pose_t is not None:
                # Z component is distance in meters.
                distance = float(selected_detection.pose_t[2][0])
            else:
                # Fallback based on pixel width
                tag_width_px = (np.linalg.norm(corners[0] - corners[1]) + np.linalg.norm(corners[2] - corners[3])) / 2.0
                fx = self.camera_params[0] if self.camera_params is not None else 500.0
                distance = (self.tag_size * fx) / max(1.0, tag_width_px)

            err_dist = distance - self.target_distance

            # --- Control Logic ---
            if abs(err_x) < self.centering_pixel_tolerance:
                angular_speed = 0.0
            else:
                angular_speed = -self.angular_kp * err_x
                angular_speed = np.clip(angular_speed, -self.max_angular_speed, self.max_angular_speed)

            if abs(err_dist) < self.distance_tolerance:
                linear_speed = 0.0
            else:
                linear_speed = self.linear_kp * err_dist
                center_factor = max(0.0, 1.0 - (abs(err_x) / (w / 2.0)))
                linear_speed *= center_factor
                linear_speed = np.clip(linear_speed, -self.max_linear_speed, self.max_linear_speed)

            cmd.linear.x = linear_speed
            cmd.angular.z = angular_speed
            self.cmd_pub.publish(cmd)

            # Stability Check for State Transition
            if abs(err_x) < self.centering_pixel_tolerance and abs(err_dist) < self.distance_tolerance:
                if self.tracking_stable_start_time is None:
                    self.tracking_stable_start_time = current_time
                elif (current_time - self.tracking_stable_start_time) >= 2.0:
                    self.get_logger().info("Target Stable for 2 seconds. Triggering PICKING sequence...")
                    self.state = 'PICKING'
                    self.execute_pick_sequence()
                    # Reset so it doesn't trigger again
                    self.tracking_stable_start_time = None
            else:
                # Reset stability timer if robot moves out of tolerance
                self.tracking_stable_start_time = None

            # Draw on image for debugging
            for i in range(4):
                p1 = tuple(corners[i].astype(int))
                p2 = tuple(corners[(i + 1) % 4].astype(int))
                cv2.line(cv_image, p1, p2, (0, 255, 0), 2)
            cv2.circle(cv_image, tuple(center.astype(int)), 5, (0, 0, 255), -1)

            info_str = f"ID: {tag_id} Dist: {distance:.2f}m ErrX: {err_x:.1f}px"
            cv2.putText(
                cv_image, info_str, (int(corners[0][0]), int(corners[0][1]) - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2
            )
            cv2.putText(
                cv_image, f"Ctrl: Lin={linear_speed:.3f} Ang={angular_speed:.3f}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2
            )

            if self.tracking_stable_start_time is not None:
                stable_time = current_time - self.tracking_stable_start_time
                cv2.putText(
                    cv_image, f"STABLE: {stable_time:.1f}s / 2.0s",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2
                )

        else:
            self.tracking_stable_start_time = None
            time_since_last_seen = current_time - self.last_tag_seen_time
            if time_since_last_seen > self.safety_timeout:
                cmd.linear.x = 0.0
                cmd.angular.z = 0.0
                self.cmd_pub.publish(cmd)
                cv2.putText(
                    cv_image, "NO TAG DETECTED - STOPPED",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2
                )

        # Overlay global state on debug image
        cv2.putText(
            cv_image, f"STATE: {self.state}",
            (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 255), 2
        )

        try:
            debug_msg = self.bridge.cv2_to_imgmsg(cv_image, encoding="bgr8")
            debug_msg.header.stamp = msg.header.stamp
            debug_msg.header.frame_id = msg.header.frame_id
            self.debug_img_pub.publish(debug_msg)
        except CvBridgeError as e:
            self.get_logger().error(f"Failed to publish debug image: {e}")

    def destroy_node(self):
        self.get_logger().info("Stopping robot and shutting down AprilTag Tracker node...")
        cmd = Twist()
        self.cmd_pub.publish(cmd)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = AprilTagTrackerNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
