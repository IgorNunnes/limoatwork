import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    # -----------------------------
    # Argumentos
    # -----------------------------
    open_rviz = DeclareLaunchArgument(
        'open_rviz',
        default_value='false',
        description='Open RViz2'
    )

    # -----------------------------
    # LIMO base
    # -----------------------------
    limo_base_node = Node(
        package='limo_base',
        executable='limo_base',
        name='limo_base',
        output='screen'
    )

    # -----------------------------
    # Hokuyo LIDAR (Ethernet)
    # -----------------------------
    urg_node = Node(
        package='urg_node',
        executable='urg_node_driver',
        name='urg_node',
        output='screen',
        parameters=[
            os.path.join(
                get_package_share_directory('urg_node'),
                'launch',
                'urg_node_ethernet.yaml'
            )
        ]
    )

    # -----------------------------
    # TF estático: base_link -> laser_frame
    # -----------------------------
#     lidar_tf_node = Node(
#         package='tf2_ros',
#         executable='static_transform_publisher',
#         name='base_to_laser_tf',
#         arguments=[
#             '0.0', '0.0', '0.20',   # x y z (ajustá si hace falta)
#             '0', '0', '0',          # roll pitch yaw
#             'base_link',
#             'laser_frame'
#         ]
#    )

    # -----------------------------
    # RViz2 (opcional)
    # -----------------------------
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2'
    )

    return LaunchDescription([
        open_rviz,
        limo_base_node,
        urg_node,
        rviz_node
    ])