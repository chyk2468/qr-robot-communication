"""
QR-Link Robotics Controller Bridge & ROS 2 Interface
Translates validated optical messages into ROS 2 topic primitives
(geometry_msgs/Twist, PoseStamped, GoalID) and simulates kinematic updates.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from protocol.message import (
    RobotCommandMessage,
    CommandType,
    NavigationParameters,
    DockParameters,
    ChargeParameters,
    ZoneAlertParameters,
)


@dataclass
class SimulatedRobotState:
    robot_id: str = "ROBOT_B_RECEIVER"
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    heading_deg: float = 0.0
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0
    battery_soc_pct: float = 85.0
    current_status: str = "IDLE_STANDBY"
    last_command_received: str = "NONE"


@dataclass
class SimulatedROS2Command:
    topic_name: str
    message_type: str
    payload_dict: Dict[str, Any]
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ExecutionResult:
    action_executed: bool
    status_summary: str
    ros2_dispatches: List[SimulatedROS2Command]
    updated_state: SimulatedRobotState


class RoboticsControllerBridge:
    """
    Translates high-level validated optical commands into simulated ROS 2
    hardware trajectory commands.
    """

    def __init__(self, initial_state: Optional[SimulatedRobotState] = None):
        self.state = initial_state or SimulatedRobotState()

    def process_command(self, message: RobotCommandMessage) -> ExecutionResult:
        dispatches = []
        status_msg = ""

        if message.command == CommandType.NAVIGATE_TO:
            params: NavigationParameters = message.parameters  # type: ignore
            # Generate Twist message
            twist_payload = {
                "linear": {"x": params.linear_velocity_max, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": params.angular_velocity_max},
            }
            dispatches.append(
                SimulatedROS2Command(
                    topic_name="/cmd_vel",
                    message_type="geometry_msgs/Twist",
                    payload_dict=twist_payload,
                )
            )

            # Generate Goal Pose
            target_coords = params.coordinates
            pose_payload = {
                "header": {"frame_id": "map", "stamp": message.timestamp_utc},
                "pose": {
                    "position": {
                        "x": target_coords.x if target_coords else 0.0,
                        "y": target_coords.y if target_coords else 0.0,
                        "z": target_coords.z if target_coords else 0.0,
                    },
                    "orientation": {"yaw_deg": target_coords.yaw_deg if target_coords else 0.0},
                },
            }
            dispatches.append(
                SimulatedROS2Command(
                    topic_name="/move_base_simple/goal",
                    message_type="geometry_msgs/PoseStamped",
                    payload_dict=pose_payload,
                )
            )

            # Update kinematics
            if target_coords:
                self.state.pos_x = target_coords.x
                self.state.pos_y = target_coords.y
                self.state.heading_deg = target_coords.yaw_deg
            self.state.linear_velocity = params.linear_velocity_max
            self.state.current_status = f"NAVIGATING_TO_{params.target_zone}"
            self.state.last_command_received = f"NAVIGATE_TO({params.target_zone})"
            status_msg = f"Navigating to zone '{params.target_zone}' at {params.linear_velocity_max} m/s."

        elif message.command == CommandType.DOCK:
            params: DockParameters = message.parameters  # type: ignore
            dispatches.append(
                SimulatedROS2Command(
                    topic_name="/docking_controller/dock_goal",
                    message_type="docking_msgs/DockGoal",
                    payload_dict={"bay_id": params.bay_id, "approach_speed": params.approach_speed},
                )
            )
            self.state.linear_velocity = params.approach_speed
            self.state.current_status = f"DOCKING_AT_{params.bay_id}"
            self.state.last_command_received = f"DOCK({params.bay_id})"
            status_msg = f"Initiating precision approach to Docking Bay '{params.bay_id}'."

        elif message.command == CommandType.CHARGE:
            params: ChargeParameters = message.parameters  # type: ignore
            dispatches.append(
                SimulatedROS2Command(
                    topic_name="/power_manager/charge_request",
                    message_type="power_msgs/ChargeRequest",
                    payload_dict={"station_id": params.station_id, "bay_index": params.bay_index},
                )
            )
            self.state.current_status = f"CHARGING_AT_{params.station_id}_BAY_{params.bay_index}"
            self.state.last_command_received = f"CHARGE({params.station_id})"
            self.state.battery_soc_pct = min(100.0, self.state.battery_soc_pct + 10.0)
            status_msg = f"Connected to charging station '{params.station_id}'."

        elif message.command == CommandType.EMERGENCY_STOP:
            # E-STOP immediately halts all actuators
            dispatches.append(
                SimulatedROS2Command(
                    topic_name="/emergency_stop",
                    message_type="std_msgs/Bool",
                    payload_dict={"data": True},
                )
            )
            dispatches.append(
                SimulatedROS2Command(
                    topic_name="/cmd_vel",
                    message_type="geometry_msgs/Twist",
                    payload_dict={"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}},
                )
            )
            self.state.linear_velocity = 0.0
            self.state.angular_velocity = 0.0
            self.state.current_status = "EMERGENCY_STOP_ENGAGED"
            self.state.last_command_received = "EMERGENCY_STOP"
            status_msg = "EMERGENCY OPTICAL E-STOP ACTIVATED. All motor drives disabled."

        elif message.command == CommandType.ZONE_ALERT:
            params: ZoneAlertParameters = message.parameters  # type: ignore
            dispatches.append(
                SimulatedROS2Command(
                    topic_name="/fleet/zone_alerts",
                    message_type="fleet_msgs/ZoneAlert",
                    payload_dict={"zone_id": params.zone_id, "alert_type": params.alert_type, "severity": params.severity.value},
                )
            )
            self.state.current_status = f"AVOIDING_HAZARD_ZONE_{params.zone_id}"
            self.state.last_command_received = f"ALERT({params.zone_id})"
            status_msg = f"Alert registered for zone '{params.zone_id}' ({params.alert_type}). Rerouting path."

        else:
            self.state.current_status = f"CUSTOM_ACTION_{message.command.value}"
            self.state.last_command_received = message.command.value
            status_msg = f"Executed custom robotic action: {message.command.value}"

        return ExecutionResult(
            action_executed=True,
            status_summary=status_msg,
            ros2_dispatches=dispatches,
            updated_state=self.state,
        )
