from geometry_msgs.msg import PoseStamped


def create_pose(x, y, z, ox, oy, oz, ow):
    pose = PoseStamped()
    pose.header.frame_id = 'map'
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.position.z = z
    pose.pose.orientation.x = ox
    pose.pose.orientation.y = oy
    pose.pose.orientation.z = oz
    pose.pose.orientation.w = ow
    return pose


pose_dict = {
    "START_DOCK": create_pose(0.94, 2.53, 0.0, 0.0, 0.0, 0.39, 0.91),
    "WS01": create_pose(0.61, -0.05, 0.0, 0.0, 0.0, -0.76, 0.64),
    "WS02": create_pose(1.85, 1.20, 0.0, 0.0, 0.0, 0.30, 0.95),
    "WS03": create_pose(1.44, 1.38, 0.0, 0.0, 0.0, 0.30, 0.95),
}
