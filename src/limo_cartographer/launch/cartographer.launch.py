from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():

    pkg_dir = get_package_share_directory('limo_cartographer')
    config_dir = os.path.join(pkg_dir, 'config')

    return LaunchDescription([

        Node(
            package='cartographer_ros',
            executable='cartographer_node',
            name='cartographer_node',
            output='screen',
            parameters=[{'use_sim_time': False}],
            arguments=[
                '-configuration_directory', config_dir,
                '-configuration_basename', 'limo_2d.lua'
            ],
            remappings=[
                ('scan', '/scan')
            ]
        ),

        Node(
            package='cartographer_ros',
            executable='cartographer_occupancy_grid_node',
            name='cartographer_occupancy_grid_node',
            output='screen',
            parameters=[
                {'resolution': 0.05},
                {'publish_period_sec': 1.0}
            ]
        )
    ])

