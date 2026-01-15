import launch
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    # -----------------------------
    # Argumentos
    # -----------------------------
    port_name_arg = DeclareLaunchArgument(
        'port_name',
        default_value='ttyUSB0',
        description='USB port name'
    )

    odom_frame_arg = DeclareLaunchArgument(
        'odom_frame',
        default_value='odom',
        description='Odometry frame'
    )

    base_link_frame_arg = DeclareLaunchArgument(
        'base_frame',
        default_value='base_link',
        description='Base link frame'
    )

    odom_topic_arg = DeclareLaunchArgument(
        'odom_topic_name',
        default_value='odom',
        description='Odometry topic'
    )

    odom_tf_arg = DeclareLaunchArgument(
        'pub_odom_tf',
        default_value='true',
        description='Publish odom TF'
    )

    control_rate_arg = DeclareLaunchArgument(
        'control_rate',
        default_value='50',
        description='Control loop rate'
    )

    # -----------------------------
    # LIMO base
    # -----------------------------
    limo_base_node = Node(
        package='limo_base',
        executable='limo_base',
        name='limo_base',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'port_name': LaunchConfiguration('port_name'),
            'odom_frame': LaunchConfiguration('odom_frame'),
            'base_frame': LaunchConfiguration('base_frame'),
            'odom_topic_name': LaunchConfiguration('odom_topic_name'),
            'pub_odom_tf': LaunchConfiguration('pub_odom_tf'),
            'control_rate': LaunchConfiguration('control_rate'),
        }]
    )

    # -----------------------------
    # TF estático: base_link -> laser
    # (LIDAR normal, 12 cm à frente)
    # -----------------------------
    lidar_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_laser_tf',
        arguments=[
            '0.12', '0.0', '0.0',   # x y z
            '0.0', '0.0', '0.0',    # roll pitch yaw
            'base_link',
            'laser'
        ]
    )

    return LaunchDescription([
        port_name_arg,
        odom_frame_arg,
        base_link_frame_arg,
        odom_topic_arg,
        odom_tf_arg,
        control_rate_arg,
        limo_base_node,
        lidar_tf_node
    ])
