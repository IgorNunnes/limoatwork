#!/usr/bin/python3
# Copyright 2020, EAIBOT
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch_ros.actions import LifecycleNode
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.actions import LogInfo

import lifecycle_msgs.msg
import os


def generate_launch_description():
    share_dir = get_package_share_directory('ydlidar_ros2_driver')
    parameter_file = LaunchConfiguration('params_file')
    base_frame = LaunchConfiguration('base_frame')
    lidar_frame = LaunchConfiguration('lidar_frame')
    lidar_x = LaunchConfiguration('lidar_x')
    lidar_y = LaunchConfiguration('lidar_y')
    lidar_z = LaunchConfiguration('lidar_z')
    lidar_roll = LaunchConfiguration('lidar_roll')
    lidar_pitch = LaunchConfiguration('lidar_pitch')
    lidar_yaw = LaunchConfiguration('lidar_yaw')
    node_name = 'ydlidar_ros2_driver_node'

    params_declare = DeclareLaunchArgument('params_file',
                                           default_value=os.path.join(
                                               share_dir, 'params', 'ydlidar.yaml'),
                                           description='FPath to the ROS2 parameters file to use.')
    base_frame_declare = DeclareLaunchArgument(
        'base_frame',
        default_value='base_link',
        description='Robot base frame used as the LiDAR TF parent.')
    lidar_frame_declare = DeclareLaunchArgument(
        'lidar_frame',
        default_value='laser_frame',
        description='LiDAR frame used by LaserScan.header.frame_id and TF child.')
    lidar_x_declare = DeclareLaunchArgument('lidar_x', default_value='0.065')
    lidar_y_declare = DeclareLaunchArgument('lidar_y', default_value='0.0')
    lidar_z_declare = DeclareLaunchArgument('lidar_z', default_value='-0.020')
    lidar_roll_declare = DeclareLaunchArgument('lidar_roll', default_value='0.0')
    lidar_pitch_declare = DeclareLaunchArgument('lidar_pitch', default_value='0.0')
    lidar_yaw_declare = DeclareLaunchArgument('lidar_yaw', default_value='0.0')

    driver_node = LifecycleNode(package='ydlidar_ros2_driver',
                                executable='ydlidar_ros2_driver_node',
                                name='ydlidar_ros2_driver_node',
                                output='screen',
                                emulate_tty=True,
                                parameters=[parameter_file, {
                                    'frame_id': lidar_frame,
                                }],
                                namespace='/',
                                )
    tf2_node = Node(package='tf2_ros',
                     executable='static_transform_publisher',
                     name='static_tf_pub_laser',
                     arguments=[
                         '--x', lidar_x,
                         '--y', lidar_y,
                         '--z', lidar_z,
                         '--roll', lidar_roll,
                         '--pitch', lidar_pitch,
                         '--yaw', lidar_yaw,
                         '--frame-id', base_frame,
                         '--child-frame-id', lidar_frame,
                     ],
                     )

    return LaunchDescription([
        params_declare,
        base_frame_declare,
        lidar_frame_declare,
        lidar_x_declare,
        lidar_y_declare,
        lidar_z_declare,
        lidar_roll_declare,
        lidar_pitch_declare,
        lidar_yaw_declare,
        driver_node,
        tf2_node,
    ])
