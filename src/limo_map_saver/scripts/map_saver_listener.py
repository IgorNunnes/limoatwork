#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty
import subprocess
import os
from datetime import datetime

class MapSaverNode(Node):
    def __init__(self):
        super().__init__('map_saver_listener')
        self.subscription = self.create_subscription(
            Empty,
            '/save_map_trigger',  # O tópico que o C++ publica
            self.listener_callback,
            10)
        self.get_logger().info('Nó "Map Saver" iniciado. Aguardando trigger no /save_map_trigger...')

    def listener_callback(self, msg):
        self.get_logger().info('Trigger (X) recebido! Salvando o mapa...')

        home_dir = os.path.expanduser('/home/solverbot/mapas')
        map_name = "mapa_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        map_path = os.path.join(home_dir, map_name) # Ex: /home/solverbot/mapa_...

        command = ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', map_path]

        try:
            subprocess.Popen(command)
            self.get_logger().info(f"Comando map_saver_cli executado. Salvando em {map_path}.yaml/.pgm")
        except Exception as e:
            self.get_logger().error(f"Falha ao executar map_saver_cli: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = MapSaverNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
