#!/usr/bin/env python3
import math
from collections import deque
from typing import List, Optional

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


def wrap_to_pi(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


class RunningStats:
    def __init__(self, maxlen: int = 50):
        self.front = deque(maxlen=maxlen)
        self.offset = deque(maxlen=maxlen)
        self.yaw = deque(maxlen=maxlen)
        self.beta = deque(maxlen=maxlen)
        self.width = deque(maxlen=maxlen)
        self.ratio = deque(maxlen=maxlen)

    def add(self, front, offset, yaw, beta, width, ratio):
        self.front.append(front)
        self.offset.append(offset)
        self.yaw.append(yaw)
        self.beta.append(beta)
        self.width.append(width)
        self.ratio.append(ratio)

    def _mean_std(self, data):
        if not data:
            return None, None
        arr = np.array(data, dtype=float)
        return float(np.mean(arr)), float(np.std(arr))

    def summary(self):
        return {
            'front': self._mean_std(self.front),
            'offset': self._mean_std(self.offset),
            'yaw': self._mean_std(self.yaw),
            'beta': self._mean_std(self.beta),
            'width': self._mean_std(self.width),
            'ratio': self._mean_std(self.ratio),
            'n': len(self.front),
        }


class LidarPoseAnalyzer(Node):
    def __init__(self):
        super().__init__('lidar_pose_analyzer')

        self.scan_msg: Optional[LaserScan] = None

        # ----------------------------
        # Parámetros
        # ----------------------------
        self.scan_topic = '/scan'
        self.front_sector_deg = 55.0
        self.min_range = 0.05
        self.max_range = 1.20

        self.cluster_gap_threshold = 0.06
        self.min_cluster_points = 12

        self.min_front_distance = 0.10
        self.max_front_distance = 0.80
        self.min_width = 0.10
        self.max_width = 0.50
        self.max_abs_beta_deg = 50.0

        self.print_period = 0.2
        self.loop_counter = 0

        # Estadísticas para calibración
        self.stats = RunningStats(maxlen=80)

        self.create_subscription(
            LaserScan,
            self.scan_topic,
            self.scan_callback,
            qos_profile_sensor_data
        )
        self.create_timer(self.print_period, self.analyze_once)

        self.get_logger().info('LidarPoseAnalyzer iniciado.')

    # ------------------------------------------------------
    # ROS
    # ------------------------------------------------------
    def scan_callback(self, msg: LaserScan):
        self.scan_msg = msg

    # ------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------
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

    def fmt(self, v: Optional[float]) -> str:
        return 'None' if v is None else f'{v:.3f}'

    # ------------------------------------------------------
    # Geometría
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

        # Cara ideal perpendicular => tangent ~ [0, 1]
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

            # Score para preferir cara frontal, cercana y estable
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
    # Análisis
    # ------------------------------------------------------
    def analyze_once(self):
        self.loop_counter += 1

        if self.scan_msg is None:
            if self.loop_counter % 5 == 0:
                self.get_logger().info('Esperando /scan...')
            return

        geom = self.analyze_geometry()
        if geom is None:
            self.get_logger().warn('No se detectó una cara válida.')
            return

        front = geom['front_distance']
        offset = geom['lateral_offset']
        yaw_deg = math.degrees(geom['yaw_error'])
        beta_deg = math.degrees(geom['beta'])
        width = geom['width_estimate']
        ratio = geom['frontal_ratio']
        pts = geom['num_points']
        centroid = geom['centroid']
        tangent = geom['tangent']
        normal = geom['normal']

        self.stats.add(front, offset, yaw_deg, beta_deg, width, ratio)
        s = self.stats.summary()

        d_m45 = self.get_distance_at_angle(-45.0)
        d_m30 = self.get_distance_at_angle(-30.0)
        d_0 = self.get_distance_at_angle(0.0)
        d_p30 = self.get_distance_at_angle(30.0)
        d_p45 = self.get_distance_at_angle(45.0)

        self.get_logger().info(
            ' | '.join([
                f'pts={pts}',
                f'front={front:.3f} m',
                f'offset_y={offset:.3f} m',
                f'yaw={yaw_deg:.2f} deg',
                f'beta={beta_deg:.2f} deg',
                f'width={width:.3f} m',
                f'ratio={ratio:.2f}',
                f'centroid=({centroid[0]:.3f},{centroid[1]:.3f})',
                f'tangent=({tangent[0]:.3f},{tangent[1]:.3f})',
                f'normal=({normal[0]:.3f},{normal[1]:.3f})',
                f'mean_yaw={self._ms(s["yaw"])}',
                f'mean_beta={self._ms(s["beta"])}',
                f'mean_offset={self._ms(s["offset"])}',
                f'rays[-45,-30,0,30,45]=[{self.fmt(d_m45)}, {self.fmt(d_m30)}, {self.fmt(d_0)}, {self.fmt(d_p30)}, {self.fmt(d_p45)}]'
            ])
        )

    def _ms(self, pair):
        mean, std = pair
        if mean is None:
            return 'None'
        return f'{mean:.2f}±{std:.2f}'


def main(args=None):
    rclpy.init(args=args)
    node = LidarPoseAnalyzer()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Nodo detenido por el usuario.')
    finally:
        summary = node.stats.summary()
        if summary['n'] > 0:
            node.get_logger().info('=== RESUMEN CALIBRACIÓN ===')
            node.get_logger().info(
                f'muestras={summary["n"]} | '
                f'front={summary["front"][0]:.4f}±{summary["front"][1]:.4f} m | '
                f'offset={summary["offset"][0]:.4f}±{summary["offset"][1]:.4f} m | '
                f'yaw={summary["yaw"][0]:.4f}±{summary["yaw"][1]:.4f} deg | '
                f'beta={summary["beta"][0]:.4f}±{summary["beta"][1]:.4f} deg | '
                f'width={summary["width"][0]:.4f}±{summary["width"][1]:.4f} m | '
                f'ratio={summary["ratio"][0]:.4f}±{summary["ratio"][1]:.4f}'
            )
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()