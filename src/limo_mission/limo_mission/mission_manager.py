from limo_mission.core.states import MissionState


class MissionManager:
    def __init__(self, node, navigator, docker):
        self.node = node
        self.navigator = navigator
        self.docker = docker

        self.state = MissionState.INIT
        self.mission_queue = []
        self.current_mission = None
        self.startup_timer = None

    def set_state(self, new_state):
        self.node.get_logger().info(
            f"STATE: {self.state.name} -> {new_state.name}"
        )
        self.state = new_state

    def add_mission(self, pose, action='goto_only'):
        self.mission_queue.append({
            'pose': pose,
            'action': action
        })

    def start(self):
        self.set_state(MissionState.SET_INITIAL_POSE)
        self.navigator.publish_initial_pose()

        self.set_state(MissionState.WAIT_LOCALIZATION)
        self.startup_timer = self.node.create_timer(4.0, self._startup_once)

    def _startup_once(self):
        if self.startup_timer is not None:
            self.startup_timer.cancel()
            self.startup_timer = None

        if self.state != MissionState.WAIT_LOCALIZATION:
            return

        self.set_state(MissionState.LOAD_NEXT_MISSION)
        self.load_next_mission()

    def load_next_mission(self):
        if not self.mission_queue:
            self.current_mission = None
            self.set_state(MissionState.FINISHED)
            self.node.get_logger().info("Todas las misiones completadas.")
            return

        self.current_mission = self.mission_queue.pop(0)
        self.set_state(MissionState.NAVIGATING)
        self.navigator.send_goal(
            self.current_mission['pose'],
            self.on_navigation_done
        )

    def on_navigation_done(self, success):
        if self.current_mission is None:
            self.set_state(MissionState.ERROR)
            self.node.get_logger().error("No hay misión actual en on_navigation_done.")
            return

        if not success:
            self.set_state(MissionState.ERROR)
            self.node.get_logger().error("Falló la navegación.")
            return

        self.node.get_logger().info("Navegación completada.")

        action = self.current_mission['action']

        if action == 'goto_only':
            self.set_state(MissionState.LOAD_NEXT_MISSION)
            self.load_next_mission()

        elif action == 'dock':
            self.set_state(MissionState.DOCKING)
            self.docker.start(done_cb=self.on_docking_done)

        else:
            self.set_state(MissionState.ERROR)
            self.node.get_logger().error(f"Acción desconocida: {action}")

    def on_docking_done(self, success):
        if self.current_mission is None:
            self.set_state(MissionState.ERROR)
            self.node.get_logger().error("No hay misión actual en on_docking_done.")
            return

        if not success:
            self.set_state(MissionState.ERROR)
            self.node.get_logger().error("Falló el docking.")
            return

        self.node.get_logger().info("Docking completado.")

        self.set_state(MissionState.LOAD_NEXT_MISSION)
        self.load_next_mission()
