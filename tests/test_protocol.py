"""
Unit tests for QR-Link Protocol & Message Validation
"""

import pytest
import json
from protocol.message import (
    RobotCommandMessage,
    CommandType,
    NavigationParameters,
    Coordinates3D,
    DockParameters,
    ChargeParameters,
)
from protocol.validator import ProtocolValidator


def test_protocol_message_instantiation():
    msg = RobotCommandMessage(
        sender_id="ROBOT_ALPHA",
        receiver_id="ROBOT_BETA",
        command=CommandType.NAVIGATE_TO,
        parameters=NavigationParameters(
            target_zone="BAY_4",
            coordinates=Coordinates3D(x=10.5, y=20.2, z=0.0, yaw_deg=90.0),
            linear_velocity_max=0.8,
        ),
    )

    assert msg.sender_id == "ROBOT_ALPHA"
    assert msg.command == CommandType.NAVIGATE_TO
    json_str = msg.to_compact_json()
    assert "BAY_4" in json_str


def test_protocol_validator_valid_json():
    msg = RobotCommandMessage(
        sender_id="ROBOT_ALPHA",
        receiver_id="BROADCAST",
        command=CommandType.DOCK,
        parameters=DockParameters(bay_id="DOCK_01", approach_speed=0.2),
    )
    raw_json = msg.to_compact_json()

    result = ProtocolValidator.validate_payload(raw_json)
    assert result.is_valid is True
    assert result.is_json is True
    assert result.message is not None
    assert result.message.command == CommandType.DOCK


def test_protocol_validator_plain_text():
    raw_text = "MOVE_FORWARD;SPEED=0.5"
    result = ProtocolValidator.validate_payload(raw_text)

    assert result.is_valid is False
    assert result.is_json is False
    assert result.errors is not None


def test_protocol_validator_invalid_bounds():
    invalid_dict = {
        "schema_version": "1.0.0",
        "sender_id": "R1",
        "receiver_id": "R2",
        "command": "NAVIGATE_TO",
        "parameters": {
            "target_zone": "Z1",
            "linear_velocity_max": 99.0,  # exceeds max 5.0 m/s
        },
    }
    raw_json = json.dumps(invalid_dict)
    result = ProtocolValidator.validate_payload(raw_json)

    assert result.is_valid is False
    assert result.errors is not None
