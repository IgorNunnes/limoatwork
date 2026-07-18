import rclpy

from limo_mission.nodes.robot_node import RobotNode
from limo_mission.core.navigator import Navigator
from limo_mission.core.docking_controller import DockingController
from limo_mission.mission_manager import MissionManager
from limo_mission.config.poses import pose_dict


def main(args=None):
    rclpy.init(args=args)

    node = RobotNode()
    navigator = Navigator(node)
    docker = DockingController(node)
    manager = MissionManager(node, navigator, docker)

    manager.add_mission(pose_dict["START_DOCK"], action='dock')
    manager.add_mission(pose_dict["WS01"], action='dock')

    manager.start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Nodo detenido por el usuario.")
    finally:
        node.destroy_node()
        rclpy.shutdown()
