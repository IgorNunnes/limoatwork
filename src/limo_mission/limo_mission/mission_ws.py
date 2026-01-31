#!/usr/bin/env python3
import math
import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult


def yaw_from_quat(z, w):
    return 2.0 * math.atan2(z, w)

def quat_from_yaw(yaw):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))

def make_pose(navigator, frame_id, x, y, z_q, w_q):
    pose = PoseStamped()
    pose.header.frame_id = frame_id
    pose.header.stamp = navigator.get_clock().now().to_msg()
    pose.pose.position.x = float(x)
    pose.pose.position.y = float(y)
    pose.pose.position.z = 0.0

    # usa yaw do quaternion fornecido (z,w) e reconstroi quaternion limpo
    yaw = yaw_from_quat(z_q, w_q)
    qx, qy, qz, qw = quat_from_yaw(yaw)
    pose.pose.orientation.x = qx
    pose.pose.orientation.y = qy
    pose.pose.orientation.z = qz
    pose.pose.orientation.w = qw
    return pose


def main():
    rclpy.init()
    navigator = BasicNavigator()

    # 1) espera Nav2 ficar ativo (BT navigator, controller, planner, etc.)
    navigator.waitUntilNav2Active()

    # 2) seus goals (assumindo frame map)
    ws = [
        ("WS1", 0.4008692310016848, -0.248988829373791, -0.6599434496136575, 0.7513152755747922),
        ("WS3", 1.5020832930994044, -0.42371004154875336, -0.03665101715179095, 0.9993281257633746),
        ("WS4", 1.3269576906278568,  1.1047995792529102,  0.028825601156226777, 0.9995844560205916),
        ("WS5", 2.4624166944846984,  2.0561498784990055, -0.9997993548541164, 0.020031226455026276),
        ("WS6", 2.7912654469940303,  1.2018443062730961,  0.08135350339121442, 0.9966853101586155),
    ]

    # 3) envia um por vez
    for name, x, y, zq, wq in ws:
        goal = make_pose(navigator, "map", x, y, zq, wq)
        print(f"\nIndo para {name}: x={x:.3f}, y={y:.3f}")
        navigator.goToPose(goal)

        while not navigator.isTaskComplete():
            feedback = navigator.getFeedback()
            if feedback:
                # só pra log simples
                pass

        result = navigator.getResult()
        if result == TaskResult.SUCCEEDED:
            print(f"{name} OK ✅")
        elif result == TaskResult.CANCELED:
            print(f"{name} cancelado ⚠️")
            break
        else:
            print(f"{name} falhou ❌")
            break

    rclpy.shutdown()


if __name__ == "__main__":
    main()

