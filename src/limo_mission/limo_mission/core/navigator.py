from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseWithCovarianceStamped


class Navigator:
    def __init__(self, node):
        self.node = node

    def publish_initial_pose(self, x=0.0, y=0.0, z=0.0, qz=0.0, qw=1.0):
        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.node.get_clock().now().to_msg()

        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        msg.pose.pose.position.z = z
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw

        msg.pose.covariance = [
            0.25, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.25, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.06853891945200942
        ]

        self.node.initial_pub.publish(msg)
        self.node.get_logger().info('Initial pose publicada.')

    def send_goal(self, pose_stamped, done_cb=None):
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = pose_stamped
        goal_msg.pose.header.stamp = self.node.get_clock().now().to_msg()

        self.node.get_logger().info("Esperando servidor navigate_to_pose...")
        self.node.nav_to_pose_client.wait_for_server()

        future = self.node.nav_to_pose_client.send_goal_async(goal_msg)

        def goal_response_callback(fut):
            goal_handle = fut.result()

            if not goal_handle.accepted:
                self.node.get_logger().error("Meta rechazada.")
                if done_cb:
                    done_cb(False)
                return

            self.node.get_logger().info("Meta aceptada.")
            result_future = goal_handle.get_result_async()

            def result_callback(res_fut):
                result = res_fut.result()
                success = (result.status == 4)
                if done_cb:
                    done_cb(success)

            result_future.add_done_callback(result_callback)

        future.add_done_callback(goal_response_callback)