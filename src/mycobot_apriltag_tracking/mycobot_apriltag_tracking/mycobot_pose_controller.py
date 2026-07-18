#!/usr/bin/env python3

import os
import time
import math

import rclpy
from rclpy.node import Node

import pymycobot
from packaging import version

MIN_REQUIRE_VERSION = '3.6.1'


class MyCobotPoseController(Node):
    def __init__(self):
        super().__init__('mycobot_pose_controller')

        current_version = pymycobot.__version__
        self.get_logger().info(f'current pymycobot library version: {current_version}')

        if version.parse(current_version) < version.parse(MIN_REQUIRE_VERSION):
            raise RuntimeError(
                f'The version of pymycobot library must be greater than {MIN_REQUIRE_VERSION}. '
                f'Current version: {current_version}'
            )

        from pymycobot import MyCobot280
        self.MyCobot280 = MyCobot280

        self.declare_parameter('port', '')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('speed', 35)
        self.declare_parameter('start_pose', 'detect')

        self.port = self.get_parameter('port').value
        self.baud = int(self.get_parameter('baud').value)
        self.speed = int(self.get_parameter('speed').value)
        self.start_pose = self.get_parameter('start_pose').value

        # Poses en radianes
        self.poses_rad = {
            'detect': [
                -0.015833339999999918,
                0.14513795999999957,
                -1.5141933600000002,
                -0.15550326000000014,
                -0.11963168999999985,
                0.7301055159999996
            ],
            'tracking': [
                0.20,
                0.10,
                -1.30,
                -0.10,
                -0.05,
                0.65
            ],
            'pick': [
                0.30,
                0.20,
                -1.60,
                -0.20,
                -0.10,
                0.75
            ]
        }

        self.mc = None
        self.started = False

        self.connect_robot()

        self.timer = self.create_timer(2.0, self.start_sequence)

    def connect_robot(self):
        port = self.port

        if not port:
            robot_m5 = os.popen("ls /dev/ttyUSB* 2>/dev/null").readline().strip()
            robot_wio = os.popen("ls /dev/ttyACM* 2>/dev/null").readline().strip()

            if robot_m5:
                port = robot_m5
            elif robot_wio:
                port = robot_wio
            else:
                raise RuntimeError('No se encontró /dev/ttyUSB* ni /dev/ttyACM* para el myCobot.')

        self.port = port
        self.get_logger().info(f'Conectando al brazo en port={self.port}, baud={self.baud}')

        self.mc = self.MyCobot280(self.port, self.baud)
        time.sleep(0.5)

        try:
            fresh_mode = self.mc.get_fresh_mode()
            self.get_logger().info(f'fresh_mode actual: {fresh_mode}')
            if fresh_mode == 0:
                self.mc.set_fresh_mode(1)
                time.sleep(0.1)
                self.get_logger().info('fresh_mode cambiado a 1')
        except Exception as e:
            self.get_logger().warn(f'No se pudo leer/configurar fresh_mode: {e}')

    def rad_to_deg_list(self, pose_rad):
        return [round(math.degrees(x), 3) for x in pose_rad]

    def go_to_pose(self, pose_name):
        if pose_name not in self.poses_rad:
            self.get_logger().error(f'Pose "{pose_name}" no existe.')
            return

        pose_rad = self.poses_rad[pose_name]
        pose_deg = self.rad_to_deg_list(pose_rad)

        self.get_logger().info(f'Yendo a pose "{pose_name}"')
        self.get_logger().info(f'Pose rad: {pose_rad}')
        self.get_logger().info(f'Pose deg: {pose_deg}')
        self.get_logger().info(f'Speed: {self.speed}')

        try:
            self.mc.send_angles(pose_deg, self.speed)
            self.get_logger().info(f'Comando enviado a pose "{pose_name}"')
        except Exception as e:
            self.get_logger().error(f'Error enviando pose "{pose_name}": {e}')

    def start_sequence(self):
        if self.started:
            return

        self.started = True

        if self.start_pose not in self.poses_rad:
            self.get_logger().warn(
                f'start_pose="{self.start_pose}" no válida. Uso detect por defecto.'
            )
            self.start_pose = 'detect'

        self.go_to_pose(self.start_pose)

    def destroy_node(self):
        self.get_logger().info('Cerrando mycobot_pose_controller')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = MyCobotPoseController()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f'[ERROR] {e}')
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()