from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='limo_apriltag_tracker',
            executable='tracker_node',
            name='apriltag_tracker_node',
            output='screen',
            parameters=[{
                'tag_family': 'tag36h11',
                'tag_size': 0.12,            # Size of the tag in meters (side length)
                'target_distance': 0.45,       # Target distance to stop at (meters)
                'distance_tolerance': 0.05,    # Tolerance for target distance (meters)
                'centering_pixel_tolerance': 20, # Tolerance for centering in camera frame (pixels)
                'target_tag_id': -1,          # Tag ID to track (-1 to track any tag)
                'linear_kp': 0.6,             # Proportional gain for linear movement
                'angular_kp': 0.0025,         # Proportional gain for angular alignment (per pixel error)
                'max_linear_speed': 0.12,     # Max linear speed (m/s)
                'max_angular_speed': 0.4,     # Max angular speed (rad/s)
            }]
        )
    ])
