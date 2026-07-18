#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState


class PoseSequencePublisher(Node):
    def __init__(self):
        super().__init__('pose_sequence_publisher')

        self.publisher_ = self.create_publisher(JointState, '/joint_states', 10)

        self.joint_names = [
            'joint2_to_joint1',
            'joint3_to_joint2',
            'joint4_to_joint3',
            'joint5_to_joint4',
            'joint6_to_joint5',
            'joint6output_to_joint6'
        ]

        self.detect_pose = [
            -0.015833339999999918,
            0.14513795999999957,
            -1.5141933600000002,
            -0.15550326000000014,
            -0.11963168999999985,
            0.7301055159999996
        ]

        self.publish_count = 0
        self.max_publish_count = 100   # 100 ciclos a 20 Hz = 5 s

        self.timer = self.create_timer(0.05, self.publish_detect_pose)

        self.get_logger().info('Publicando pose detect a 20 Hz...')

    def publish_detect_pose(self):
        if self.publish_count >= self.max_publish_count:
            self.get_logger().info('Fin de publicación.')
            self.timer.cancel()
            return

        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = self.joint_names
        msg.position = self.detect_pose
        msg.velocity = []
        msg.effort = []

        self.publisher_.publish(msg)
        self.publish_count += 1

        if self.publish_count % 20 == 0:
            self.get_logger().info(f'Pose detect publicada {self.publish_count} veces')


def main(args=None):
    rclpy.init(args=args)
    node = PoseSequencePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()