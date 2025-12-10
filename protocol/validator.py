"""
QR-Link Protocol Validator Module
Enforces schema constraints, field boundaries, and formats error diagnostics.
"""

import json
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any
from pydantic import ValidationError

from .message import (
    RobotCommandMessage,
    CommandType,
    NavigationParameters,
    DockParameters,
    ChargeParameters,
    ZoneAlertParameters,
    CustomParameters,
)


@dataclass
class ValidationResult:
    is_valid: bool
    message: Optional[RobotCommandMessage] = None
    is_json: bool = False
    raw_dict: Optional[Dict[str, Any]] = None
    errors: Optional[List[str]] = None
    warning_notes: Optional[List[str]] = None


class ProtocolValidator:
    """
    Validates raw incoming strings or decoded QR text against the QR-Link protocol standard.
    """

    @staticmethod
    def validate_payload(raw_text: str) -> ValidationResult:
        if not raw_text or not raw_text.strip():
            return ValidationResult(
                is_valid=False,
                errors=["Empty payload received."],
            )

        # 1. Attempt JSON parsing
        try:
            payload_dict = json.loads(raw_text.strip())
        except json.JSONDecodeError:
            # It's plain text or delimited key-value, not structured JSON
            return ValidationResult(
                is_valid=False,
                is_json=False,
                errors=["Payload is not valid JSON. Interpreted as unstructured legacy text."],
                warning_notes=["Consider upgrading the transmitting agent to JSON protocol v1.0.0."],
            )

        # 2. Attempt Pydantic Model Validation
        try:
            cmd_type = payload_dict.get("command")
            params = payload_dict.get("parameters", {})

            # Ensure correct parameter subtype resolution
            if cmd_type == CommandType.NAVIGATE_TO.value:
                payload_dict["parameters"] = NavigationParameters(**params)
            elif cmd_type == CommandType.DOCK.value:
                payload_dict["parameters"] = DockParameters(**params)
            elif cmd_type == CommandType.CHARGE.value:
                payload_dict["parameters"] = ChargeParameters(**params)
            elif cmd_type == CommandType.ZONE_ALERT.value:
                payload_dict["parameters"] = ZoneAlertParameters(**params)
            elif cmd_type == CommandType.EMERGENCY_STOP.value:
                # Emergency stop can use minimal custom params
                if not params:
                    payload_dict["parameters"] = CustomParameters(action="EMERGENCY_STOP", arguments={"reason": "Immediate optical E-STOP triggered"})
                else:
                    payload_dict["parameters"] = CustomParameters(**params)
            elif cmd_type == CommandType.CUSTOM.value:
                payload_dict["parameters"] = CustomParameters(**params)

            robot_msg = RobotCommandMessage(**payload_dict)

            warnings = []
            if robot_msg.receiver_id == "BROADCAST":
                warnings.append("Message destination is BROADCAST (all optical receivers will process).")

            return ValidationResult(
                is_valid=True,
                message=robot_msg,
                is_json=True,
                raw_dict=payload_dict,
                errors=None,
                warning_notes=warnings if warnings else None,
            )

        except ValidationError as ve:
            error_list = [f"{err['loc']}: {err['msg']}" for err in ve.errors()]
            return ValidationResult(
                is_valid=False,
                is_json=True,
                raw_dict=payload_dict,
                errors=error_list,
            )
        except Exception as ex:
            return ValidationResult(
                is_valid=False,
                is_json=True,
                raw_dict=payload_dict,
                errors=[f"Protocol parse exception: {str(ex)}"],
            )


def validate_protocol_message(raw_text: str) -> ValidationResult:
    """Convenience function for validating raw payload text."""
    return ProtocolValidator.validate_payload(raw_text)
