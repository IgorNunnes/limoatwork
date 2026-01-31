#!/usr/bin/env python3
import math
import yaml
import threading
from dataclasses import dataclass
from typing import Dict

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from geometry_msgs.msg import PoseStamped, Point, Quaternion
from nav2_msgs.action import NavigateToPose, BackUp
from limo_mission_msgs.action import Dock
from action_msgs.msg import GoalStatus


@dataclass
class Waypoint:
    name: str
    x: float
    y: float
    yaw: float


def yaw_to_quat(yaw: float) -> Quaternion:
    q = Quaternion()
    q.w = math.cos(yaw / 2.0)
    q.z = math.sin(yaw / 2.0)
    q.x = 0.0
    q.y = 0.0
    return q


class MissionManager(Node):
    def __init__(self):
        super().__init__("mission_manager")

        # =========================
        # Params
        # =========================
        self.declare_parameter("waypoints_yaml", "config/waypoints.yaml")
        self.declare_parameter("route_name", "test_route")

        self.declare_parameter("dock_retries", 2)
        self.declare_parameter("nav_timeout_sec", 120.0)
        self.declare_parameter("dock_timeout_sec", 60.0)

        self.declare_parameter("backup_distance", 0.10)
        self.declare_parameter("backup_speed", 0.08)
        self.declare_parameter("backup_timeout_sec", 3.0)

        # Dock params (defaults bons)
        self.declare_parameter("dock_target_offset_x", 0.05)  # 5cm
        self.declare_parameter("dock_max_scan_range", 2.5)
        self.declare_parameter("dock_fov_deg", 120.0)

        self.declare_parameter("dock_kx", 0.8)
        self.declare_parameter("dock_ky", 2.0)
        self.declare_parameter("dock_ktheta", 1.5)

        self.declare_parameter("dock_tol_x", 0.01)
        self.declare_parameter("dock_tol_y", 0.01)
        self.declare_parameter("dock_tol_yaw_deg", 1.0)

        self.declare_parameter("dock_v_max", 0.08)
        self.declare_parameter("dock_w_max", 0.7)

        # Load waypoints
        self.route_name = self.get_parameter("route_name").value
        wp_path = self.get_parameter("waypoints_yaml").value

        self.frame_id, self.wp_map, self.route = self._load_waypoints_and_route(wp_path, self.route_name)
        if not self.route:
            raise RuntimeError(f"Rota '{self.route_name}' vazia ou inexistente no YAML.")

        self.get_logger().info(
            f"frame_id='{self.frame_id}', route='{self.route_name}' com {len(self.route)} WS: {self.route}"
        )

        # Action clients
        self.nav_client = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self.backup_client = ActionClient(self, BackUp, "/backup")
        self.dock_client = ActionClient(self, Dock, "/dock")

        # ✅ Start mission in a separate thread (robusto)
        threading.Thread(target=self._run_mission, daemon=True).start()

    # -------------------------
    # YAML loader
    # -------------------------
    def _load_waypoints_and_route(self, path: str, route_name: str):
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        frame_id = data.get("frame_id", "map")

        wp_raw: Dict[str, dict] = data.get("waypoints", {})
        wp_map: Dict[str, Waypoint] = {}
        for name, v in wp_raw.items():
            wp_map[name] = Waypoint(
                name=name,
                x=float(v["x"]),
                y=float(v["y"]),
                yaw=float(v["yaw"]),
            )

        routes = data.get("routes", {})
        route_list = routes.get(route_name, [])
        for ws_name in route_list:
            if ws_name not in wp_map:
                raise RuntimeError(f"WS '{ws_name}' na rota '{route_name}' não existe em waypoints.")

        return frame_id, wp_map, route_list

    # -------------------------
    # Pose helper
    # -------------------------
    def _pose_stamped(self, x: float, y: float, yaw: float) -> PoseStamped:
        ps = PoseStamped()
        ps.header.frame_id = self.frame_id
        # ✅ stamp 0 (evita reject por desync/sim_time)
        ps.header.stamp.sec = 0
        ps.header.stamp.nanosec = 0
        ps.pose.position.x = x
        ps.pose.position.y = y
        ps.pose.position.z = 0.0
        ps.pose.orientation = yaw_to_quat(yaw)
        return ps

    # -------------------------
    # Action helpers
    # -------------------------
    def _wait_server(self, client: ActionClient, name: str, timeout_sec: float = 10.0) -> bool:
        if not client.wait_for_server(timeout_sec=timeout_sec):
            self.get_logger().error(f"Action server {name} não disponível.")
            return False
        return True

    def _send_goal_and_wait(self, client: ActionClient, goal_msg, timeout_sec: float) -> bool:
        # 1) Espera resposta do goal (aceito/rejeitado)
        send_future = client.send_goal_async(goal_msg)

        goal_response_timeout = 30.0
        rclpy.spin_until_future_complete(self, send_future, timeout_sec=goal_response_timeout)

        if not send_future.done():
            self.get_logger().error(
                f"Timeout ({goal_response_timeout}s) esperando resposta do goal."
            )
            return False

        gh = send_future.result()
        if gh is None:
            self.get_logger().error("Não recebeu GoalHandle (None).")
            return False

        if not gh.accepted:
            self.get_logger().error("Goal rejeitado pelo servidor (accepted=False).")
            return False

        # 2) Espera resultado final
        result_future = gh.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=timeout_sec)

        if not result_future.done():
            self.get_logger().error("Timeout esperando resultado. Cancelando...")
            cancel_future = gh.cancel_goal_async()
            rclpy.spin_until_future_complete(self, cancel_future, timeout_sec=2.0)
            return False

        status = result_future.result().status
        return status == GoalStatus.STATUS_SUCCEEDED

    # -------------------------
    # Dock goal builder
    # -------------------------
    def _make_dock_goal(self, dock_timeout: float) -> Dock.Goal:
        g = Dock.Goal()
        g.target_offset_x = float(self.get_parameter("dock_target_offset_x").value)
        g.max_scan_range = float(self.get_parameter("dock_max_scan_range").value)
        g.fov_deg = float(self.get_parameter("dock_fov_deg").value)

        g.kx = float(self.get_parameter("dock_kx").value)
        g.ky = float(self.get_parameter("dock_ky").value)
        g.ktheta = float(self.get_parameter("dock_ktheta").value)

        g.tol_x = float(self.get_parameter("dock_tol_x").value)
        g.tol_y = float(self.get_parameter("dock_tol_y").value)
        g.tol_yaw_deg = float(self.get_parameter("dock_tol_yaw_deg").value)

        g.v_max = float(self.get_parameter("dock_v_max").value)
        g.w_max = float(self.get_parameter("dock_w_max").value)

        g.timeout_sec = float(dock_timeout)
        return g

    # -------------------------
    # Mission loop
    # -------------------------
    def _run_mission(self):
        # Aguarda estabilização inicial
        self.get_logger().info("Aguardando estabilização (2s) antes do primeiro goal...")
        rclpy.spin_once(self, timeout_sec=2.0)

        dock_retries = int(self.get_parameter("dock_retries").value)
        nav_timeout = float(self.get_parameter("nav_timeout_sec").value)
        dock_timeout = float(self.get_parameter("dock_timeout_sec").value)

        backup_distance = float(self.get_parameter("backup_distance").value)
        backup_speed = float(self.get_parameter("backup_speed").value)
        backup_timeout = float(self.get_parameter("backup_timeout_sec").value)

        # Wait action servers
        if not self._wait_server(self.nav_client, "/navigate_to_pose"):
            return
        if not self._wait_server(self.backup_client, "/backup"):
            return
        if not self._wait_server(self.dock_client, "/dock"):
            self.get_logger().warn("Dock server (/dock) não disponível. Suba teu docking server antes.")
            return

        for i, ws_name in enumerate(self.route, start=1):
            wp = self.wp_map[ws_name]
            self.get_logger().info(
                f"[{i}/{len(self.route)}] Indo para {wp.name} (x={wp.x:.3f}, y={wp.y:.3f}, yaw={wp.yaw:.3f})"
            )

            # 1) NavigateToPose
            nav_goal = NavigateToPose.Goal()
            nav_goal.pose = self._pose_stamped(wp.x, wp.y, wp.yaw)

            if not self._send_goal_and_wait(self.nav_client, nav_goal, timeout_sec=nav_timeout):
                self.get_logger().error(f"{wp.name}: navegação falhou. Pulando.")
                continue

            # 2) Dock
            dock_ok = False
            for attempt in range(1, dock_retries + 1):
                self.get_logger().info(f"{wp.name}: docking tentativa {attempt}/{dock_retries}")
                dock_goal = self._make_dock_goal(dock_timeout)

                if self._send_goal_and_wait(self.dock_client, dock_goal, timeout_sec=dock_timeout + 5.0):
                    dock_ok = True
                    break

            if not dock_ok:
                self.get_logger().error(f"{wp.name}: docking falhou. Indo para próxima WS.")
                continue

            # 3) BackUp (undock)
            self.get_logger().info(f"{wp.name}: undock (backup {backup_distance:.2f} m)")
            b = BackUp.Goal()
            b.target = Point(x=abs(backup_distance), y=0.0, z=0.0)
            b.speed = float(backup_speed)
            b.time_allowance.sec = int(backup_timeout)
            b.time_allowance.nanosec = 0

            if not self._send_goal_and_wait(self.backup_client, b, timeout_sec=backup_timeout + 5.0):
                self.get_logger().warn(f"{wp.name}: backup falhou (seguindo mesmo assim).")

            self.get_logger().info(f"{wp.name}: OK ✅")

        self.get_logger().info("Rota finalizada ✅")


def main():
    rclpy.init()
    node = MissionManager()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
