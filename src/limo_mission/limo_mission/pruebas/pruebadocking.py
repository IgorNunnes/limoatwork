#!/usr/bin/env python3
import math
from enum import Enum, auto
from typing import List, Optional

import numpy as np
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


def clamp(value: float, vmin: float, vmax: float) -> float:
    return max(vmin, min(value, vmax))


def wrap_to_pi(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


class DockState(Enum):
    SEARCH = auto()
    ALIGNING_COARSE = auto()
    ALIGNING_FINE = auto()
    RECENTER_FOR_DOCK = auto()
    APPROACHING = auto()
    DONE = auto()


class DockWindow(Enum):
    READY_FOR_DOCK = auto()
    ESCAPED_LEFT = auto()
    ESCAPED_RIGHT = auto()


class LidarDockApproach(Node):
    def __init__(self):
        super().__init__('lidar_dock_approach')

        # ----------------------------
        # Topics
        # ----------------------------
        self.scan_topic = '/scan'
        self.cmd_topic = '/cmd_vel'

        self.scan_msg: Optional[LaserScan] = None

        self.create_subscription(
            LaserScan,
            self.scan_topic,
            self.scan_callback,
            qos_profile_sensor_data
        )
        self.cmd_pub = self.create_publisher(Twist, self.cmd_topic, 10)

        # ----------------------------
        # LiDAR / cluster params
        # ----------------------------
        self.front_sector_deg = 55.0
        self.min_range = 0.05
        self.max_range = 1.20

        self.cluster_gap_threshold = 0.06
        self.min_cluster_points = 12

        self.min_front_distance = 0.08
        self.max_front_distance = 0.80
        self.min_width = 0.10
        self.max_width = 0.50
        self.max_abs_beta_deg = 45.0

        # ----------------------------
        # Target docking distance
        # ----------------------------
        self.target_distance = 0.10

        # ----------------------------
        # Ventana apta para docking
        # ----------------------------
        self.ready_offset_tol = 0.040
        self.escape_offset_tol = 0.055

        self.ready_beta_deg = 12.0
        self.escape_beta_deg = 15.0

        self.ready_ratio_max = 1.25
        self.escape_ratio_max = 1.35

        # ----------------------------
        # Control COARSE
        # ----------------------------
        self.k_yaw_coarse = 1.8
        self.max_w_coarse = 0.35
        self.min_w_coarse = 0.06

        self.coarse_to_fine_deg = 6.0
        self.coarse_exit_deg = 10.0

        # ----------------------------
        # Control FINE
        # ----------------------------
        self.k_yaw_fine = 1.5
        self.max_w_fine = 0.15
        self.min_w_fine = 0.04

        self.align_tol_fine_deg = 1.4
        self.align_exit_tol_fine_deg = 2.2
        self.aligned_required_cycles_fine = 8

        # ----------------------------
        # Control RECENTER (omni en Y)
        # ----------------------------
        self.k_y_recenter = 1.2
        self.max_vy_recenter = 0.10
        self.min_vy_recenter = 0.03
        self.recenter_stop_tol = 0.020

        self.k_yaw_recenter = 0.6
        self.max_w_recenter = 0.08

        # Si el movimiento lateral sale al lado incorrecto, cambia esto a True
        self.invert_y_axis = False

        # ----------------------------
        # Control APPROACH
        # ----------------------------
        self.k_dist = 0.9
        self.max_v_approach = 0.14
        self.min_v_approach = 0.025

        self.k_yaw_approach = 0.8
        self.max_w_approach = 0.10

        # si se desalinea mucho durante el approach, volver a fine align
        self.approach_exit_yaw_deg = 2.5

        # tolerancia final
        self.done_dist_tol = 0.01
        self.done_yaw_tol_deg = 1.2
        self.done_required_cycles = 8
        self.done_counter = 0

        # SEARCH
        self.search_w = 0.12

        # Si gira al lado incorrecto, invierte esto
        self.invert_yaw_sign = True

        # ----------------------------
        # Filtering
        # ----------------------------
        self.filter_alpha_coarse = 0.80
        self.filter_alpha_fine = 0.65
        self.filter_alpha_approach = 0.70
        self.filter_alpha_recenter = 0.70

        self.filtered_yaw = None
        self.filtered_front = None
        self.filtered_offset = None
        self.filtered_beta = None

        # ----------------------------
        # Runtime
        # ----------------------------
        self.state = DockState.SEARCH
        self.aligned_counter = 0
        self.loop_counter = 0
        self.invalid_geom_counter = 0
        self.invalid_geom_limit = 6

        # ----------------------------
        # Calibración real: posiciones perfectas
        # yaw_target = f(beta)
        # ----------------------------
        self.cal_beta_deg = np.array([
            -9.3830,
             6.6162,
            27.0619
        ], dtype=float)

        self.cal_yaw_deg = np.array([
            -0.9740,
            -3.1917,
            -4.7687
        ], dtype=float)

        self.create_timer(0.05, self.control_loop)

        self.get_logger().info('LidarDockApproach iniciado.')

    # ------------------------------------------------------
    # ROS callbacks
    # ------------------------------------------------------
    def scan_callback(self, msg: LaserScan):
        self.scan_msg = msg

    # ------------------------------------------------------
    # Utils
    # ------------------------------------------------------
    def set_state(self, new_state: DockState):
        if new_state != self.state:
            self.get_logger().info(f'STATE: {self.state.name} -> {new_state.name}')
            self.state = new_state
            self.aligned_counter = 0
            self.done_counter = 0

    def publish_cmd(self, vx: float, vy: float, w: float):
        cmd = Twist()
        cmd.linear.x = float(vx)
        cmd.linear.y = float(vy)
        cmd.angular.z = float(w)
        self.cmd_pub.publish(cmd)

    def stop_robot(self):
        if rclpy.ok():
            self.publish_cmd(0.0, 0.0, 0.0)

    def lowpass(self, old_value, new_value, alpha):
        if old_value is None:
            return new_value
        return alpha * old_value + (1.0 - alpha) * new_value

    def get_distance_at_angle(self, target_angle_deg: float) -> Optional[float]:
        scan = self.scan_msg
        if scan is None:
            return None

        if scan.angle_increment == 0.0:
            return None

        angle_rad = math.radians(target_angle_deg)
        idx = int((angle_rad - scan.angle_min) / scan.angle_increment)

        if 0 <= idx < len(scan.ranges):
            r = scan.ranges[idx]
            max_valid = min(self.max_range, scan.range_max)
            if self.min_range < r < max_valid:
                return float(r)

        return None

    def yaw_target_from_beta(self, beta_deg: float) -> float:
        return float(np.interp(
            beta_deg,
            self.cal_beta_deg,
            self.cal_yaw_deg,
            left=self.cal_yaw_deg[0],
            right=self.cal_yaw_deg[-1]
        ))

    # ------------------------------------------------------
    # Geometry extraction
    # ------------------------------------------------------
    def extract_points(self) -> List[np.ndarray]:
        scan = self.scan_msg
        if scan is None:
            return []

        points = []
        sector_rad = math.radians(self.front_sector_deg)
        max_valid = min(self.max_range, scan.range_max)

        for i, r in enumerate(scan.ranges):
            if not (self.min_range < r < max_valid):
                continue

            theta = scan.angle_min + i * scan.angle_increment
            if abs(theta) > sector_rad:
                continue

            x = r * math.cos(theta)
            y = r * math.sin(theta)
            points.append(np.array([x, y], dtype=float))

        return points

    def split_into_clusters(self, points: List[np.ndarray]) -> List[np.ndarray]:
        if not points:
            return []

        clusters = []
        current = [points[0]]

        for i in range(1, len(points)):
            d = np.linalg.norm(points[i] - points[i - 1])
            if d > self.cluster_gap_threshold:
                if len(current) >= self.min_cluster_points:
                    clusters.append(np.array(current))
                current = [points[i]]
            else:
                current.append(points[i])

        if len(current) >= self.min_cluster_points:
            clusters.append(np.array(current))

        return clusters

    def fit_face_pca(self, cluster: np.ndarray):
        centroid = cluster.mean(axis=0)
        centered = cluster - centroid
        cov = np.cov(centered.T)

        eigvals, eigvecs = np.linalg.eigh(cov)

        tangent = eigvecs[:, np.argmax(eigvals)]
        tangent = tangent / np.linalg.norm(tangent)

        if tangent[1] < 0.0:
            tangent = -tangent

        normal = np.array([tangent[1], -tangent[0]], dtype=float)
        normal = normal / np.linalg.norm(normal)

        if normal[0] < 0.0:
            normal = -normal

        front_distance = float(np.dot(normal, centroid))
        lateral_offset = float(centroid[1])

        yaw_error = math.atan2(tangent[0], tangent[1])
        yaw_error = wrap_to_pi(yaw_error)

        beta = math.atan2(centroid[1], centroid[0])

        projections = centered @ tangent
        width_estimate = float(projections.max() - projections.min())

        ray0 = self.get_distance_at_angle(0.0)
        frontal_ratio = float('inf')
        if ray0 is not None and front_distance > 1e-6:
            frontal_ratio = float(ray0 / front_distance)

        return {
            'centroid': centroid,
            'tangent': tangent,
            'normal': normal,
            'front_distance': front_distance,
            'lateral_offset': lateral_offset,
            'yaw_error': yaw_error,
            'beta': beta,
            'width_estimate': width_estimate,
            'num_points': int(len(cluster)),
            'ray0': ray0,
            'frontal_ratio': frontal_ratio,
        }

    def cluster_is_valid(self, geom) -> bool:
        if geom is None:
            return False

        pts = geom['num_points']
        front = geom['front_distance']
        width = geom['width_estimate']
        beta_deg = abs(math.degrees(geom['beta']))
        ratio = geom['frontal_ratio']

        if pts < self.min_cluster_points:
            return False
        if not (self.min_front_distance <= front <= self.max_front_distance):
            return False
        if not (self.min_width <= width <= self.max_width):
            return False
        if beta_deg > self.max_abs_beta_deg:
            return False
        if not math.isfinite(ratio):
            return False

        return True

    def choose_box_cluster(self, clusters: List[np.ndarray]) -> Optional[np.ndarray]:
        if not clusters:
            return None

        candidates = []

        for cluster in clusters:
            geom = self.fit_face_pca(cluster)
            if not self.cluster_is_valid(geom):
                continue

            front = geom['front_distance']
            beta = abs(geom['beta'])
            width = geom['width_estimate']
            pts = geom['num_points']

            score = (
                2.0 * front
                + 0.6 * abs(beta)
                + 0.3 * abs(width - 0.25)
                - 0.002 * pts
            )
            candidates.append((score, cluster))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def analyze_geometry(self):
        points = self.extract_points()
        if len(points) < self.min_cluster_points:
            return None

        clusters = self.split_into_clusters(points)
        if not clusters:
            return None

        cluster = self.choose_box_cluster(clusters)
        if cluster is None:
            return None

        geom = self.fit_face_pca(cluster)
        if not self.cluster_is_valid(geom):
            return None

        return geom

    # ------------------------------------------------------
    # Clasificación de situación lateral
    # ------------------------------------------------------
    def classify_dock_window(self, offset: float, beta_deg: float, ratio: float, ray0: Optional[float]) -> DockWindow:
        ready = (
            abs(offset) < self.ready_offset_tol and
            abs(beta_deg) < self.ready_beta_deg and
            ratio < self.ready_ratio_max and
            ray0 is not None
        )

        if ready:
            return DockWindow.READY_FOR_DOCK

        sign_metric = offset + 0.002 * beta_deg

        # escapada lateral
        escaped = (
            abs(offset) > self.escape_offset_tol or
            abs(beta_deg) > self.escape_beta_deg or
            ratio > self.escape_ratio_max or
            ray0 is None
        )

        if escaped:
            if sign_metric >= 0.0:
                return DockWindow.ESCAPED_LEFT
            return DockWindow.ESCAPED_RIGHT

        # si no está claramente escapada, tratarla como ready
        return DockWindow.READY_FOR_DOCK

    # ------------------------------------------------------
    # Control loop
    # ------------------------------------------------------
    def control_loop(self):
        self.loop_counter += 1

        if self.scan_msg is None:
            if self.loop_counter % 10 == 0:
                self.get_logger().info('Esperando /scan...')
            self.stop_robot()
            return

        geom = self.analyze_geometry()
        if geom is None:
            self.invalid_geom_counter += 1

            if self.invalid_geom_counter >= self.invalid_geom_limit:
                self.set_state(DockState.SEARCH)
                self.publish_cmd(0.0, 0.0, self.search_w)

            if self.loop_counter % 10 == 0:
                self.get_logger().warn('Geometría inválida o cluster inestable.')
            return

        self.invalid_geom_counter = 0

        raw_yaw = geom['yaw_error']
        raw_front = geom['front_distance']
        raw_offset = geom['lateral_offset']
        raw_beta = geom['beta']

        pts = geom['num_points']
        width = geom['width_estimate']
        ratio = geom['frontal_ratio']
        ray0 = geom['ray0']

        if self.state == DockState.ALIGNING_FINE:
            alpha = self.filter_alpha_fine
        elif self.state == DockState.APPROACHING:
            alpha = self.filter_alpha_approach
        elif self.state == DockState.RECENTER_FOR_DOCK:
            alpha = self.filter_alpha_recenter
        else:
            alpha = self.filter_alpha_coarse

        self.filtered_yaw = self.lowpass(self.filtered_yaw, raw_yaw, alpha)
        self.filtered_front = self.lowpass(self.filtered_front, raw_front, alpha)
        self.filtered_offset = self.lowpass(self.filtered_offset, raw_offset, alpha)
        self.filtered_beta = self.lowpass(self.filtered_beta, raw_beta, alpha)

        yaw = self.filtered_yaw
        front = self.filtered_front
        offset = self.filtered_offset
        beta = self.filtered_beta

        yaw_deg = math.degrees(yaw)
        beta_deg = math.degrees(beta)

        yaw_target_deg = self.yaw_target_from_beta(beta_deg)
        yaw_corr_deg = yaw_deg - yaw_target_deg
        yaw_corr_rad = math.radians(yaw_corr_deg)

        yaw_control_coarse = -yaw if self.invert_yaw_sign else yaw
        yaw_control_fine = -yaw_corr_rad if self.invert_yaw_sign else yaw_corr_rad

        dist_error = front - self.target_distance

        dock_window = self.classify_dock_window(offset, beta_deg, ratio, ray0)

        # ----------------------------
        # State transitions
        # ----------------------------
        if self.state == DockState.SEARCH:
            self.set_state(DockState.ALIGNING_COARSE)

        elif self.state == DockState.ALIGNING_COARSE:
            if abs(yaw_corr_deg) < self.coarse_to_fine_deg:
                self.set_state(DockState.ALIGNING_FINE)

        elif self.state == DockState.ALIGNING_FINE:
            if abs(yaw_corr_deg) > self.coarse_exit_deg:
                self.set_state(DockState.ALIGNING_COARSE)
            elif dock_window != DockWindow.READY_FOR_DOCK:
                self.set_state(DockState.RECENTER_FOR_DOCK)
            else:
                if abs(yaw_corr_deg) < self.align_tol_fine_deg:
                    self.aligned_counter += 1
                elif abs(yaw_corr_deg) > self.align_exit_tol_fine_deg:
                    self.aligned_counter = 0

                if (
                    self.aligned_counter >= self.aligned_required_cycles_fine
                    or (abs(yaw_corr_deg) < 1.8 and dist_error > 0.02)
                ):
                    self.set_state(DockState.APPROACHING)

        elif self.state == DockState.RECENTER_FOR_DOCK:
            if abs(yaw_corr_deg) > self.coarse_exit_deg:
                self.set_state(DockState.ALIGNING_COARSE)
            elif dock_window == DockWindow.READY_FOR_DOCK:
                if abs(yaw_corr_deg) < 1.8 and dist_error > 0.02:
                    self.set_state(DockState.APPROACHING)
                else:
                    self.set_state(DockState.ALIGNING_FINE)

        elif self.state == DockState.APPROACHING:
            if abs(yaw_corr_deg) > self.approach_exit_yaw_deg:
                self.set_state(DockState.ALIGNING_FINE)
            elif dock_window != DockWindow.READY_FOR_DOCK:
                self.set_state(DockState.RECENTER_FOR_DOCK)
            else:
                if abs(dist_error) < self.done_dist_tol and abs(yaw_corr_deg) < self.done_yaw_tol_deg:
                    self.done_counter += 1
                else:
                    self.done_counter = 0

                if self.done_counter >= self.done_required_cycles:
                    self.set_state(DockState.DONE)

        elif self.state == DockState.DONE:
            if abs(yaw_corr_deg) > self.approach_exit_yaw_deg:
                self.set_state(DockState.ALIGNING_FINE)
            elif dock_window != DockWindow.READY_FOR_DOCK:
                self.set_state(DockState.RECENTER_FOR_DOCK)

        # ----------------------------
        # Control
        # ----------------------------
        vx = 0.0
        vy = 0.0
        w = 0.0

        if self.state == DockState.SEARCH:
            w = self.search_w

        elif self.state == DockState.ALIGNING_COARSE:
            w = clamp(self.k_yaw_coarse * yaw_control_coarse, -self.max_w_coarse, self.max_w_coarse)

            if abs(yaw_corr_deg) > self.coarse_to_fine_deg and abs(w) < self.min_w_coarse:
                w = math.copysign(self.min_w_coarse, w)

        elif self.state == DockState.ALIGNING_FINE:
            w = clamp(self.k_yaw_fine * yaw_control_fine, -self.max_w_fine, self.max_w_fine)

            if abs(yaw_corr_deg) > 0.20 and abs(w) < self.min_w_fine:
                w = math.copysign(self.min_w_fine, w)

            if abs(yaw_corr_deg) < 0.15:
                w = 0.0

        elif self.state == DockState.RECENTER_FOR_DOCK:
            lateral_error = offset

            vy = clamp(self.k_y_recenter * lateral_error, -self.max_vy_recenter, self.max_vy_recenter)

            if self.invert_y_axis:
                vy = -vy

            if abs(lateral_error) > self.recenter_stop_tol and abs(vy) < self.min_vy_recenter:
                vy = math.copysign(self.min_vy_recenter, vy)

            if abs(lateral_error) < self.recenter_stop_tol:
                vy = 0.0

            w = clamp(self.k_yaw_recenter * yaw_control_fine, -self.max_w_recenter, self.max_w_recenter)

        elif self.state == DockState.APPROACHING:
            # mantenemos el avance en x
            if dist_error > self.done_dist_tol:
                vx = clamp(self.k_dist * dist_error, self.min_v_approach, self.max_v_approach)
            else:
                vx = 0.0

            w = clamp(self.k_yaw_approach * yaw_control_fine, -self.max_w_approach, self.max_w_approach)

        elif self.state == DockState.DONE:
            vx = 0.0
            vy = 0.0
            w = 0.0

        self.publish_cmd(vx, vy, w)

        # ----------------------------
        # Debug
        # ----------------------------
        if self.loop_counter % 4 == 0:
            d_m45 = self.get_distance_at_angle(-45.0)
            d_m30 = self.get_distance_at_angle(-30.0)
            d_0 = self.get_distance_at_angle(0.0)
            d_p30 = self.get_distance_at_angle(30.0)
            d_p45 = self.get_distance_at_angle(45.0)

            self.get_logger().info(
                ' | '.join([
                    f'state={self.state.name}',
                    f'window={dock_window.name}',
                    f'pts={pts}',
                    f'front={front:.3f}',
                    f'dist_err={dist_error:.3f}',
                    f'offset={offset:.3f}',
                    f'yaw_raw={yaw_deg:.2f}deg',
                    f'beta={beta_deg:.2f}deg',
                    f'yaw_target={yaw_target_deg:.2f}deg',
                    f'yaw_corr={yaw_corr_deg:.2f}deg',
                    f'width={width:.3f}',
                    f'ratio={ratio:.2f}',
                    f'cmd=({vx:.3f},{vy:.3f},{w:.3f})',
                    f'aligned={self.aligned_counter}',
                    f'done={self.done_counter}',
                    f'rays[-45,-30,0,30,45]=[{self._fmt(d_m45)}, {self._fmt(d_m30)}, {self._fmt(d_0)}, {self._fmt(d_p30)}, {self._fmt(d_p45)}]'
                ])
            )

    def _fmt(self, value: Optional[float]) -> str:
        return 'None' if value is None else f'{value:.3f}'


def main(args=None):
    rclpy.init(args=args)
    node = LidarDockApproach()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Nodo detenido por el usuario.')
    finally:
        try:
            if rclpy.ok():
                node.stop_robot()
        except Exception:
            pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()