"""
QR-Link Robotics Protocol Message Schemas
Defines type-safe Pydantic models for structured robot-to-robot commands.
"""

from enum import Enum
from typing import Optional, Dict, Any, Union
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class CommandType(str, Enum):
    NAVIGATE_TO = "NAVIGATE_TO"
    DOCK = "DOCK"
    CHARGE = "CHARGE"
    ZONE_ALERT = "ZONE_ALERT"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    CUSTOM = "CUSTOM"


class PriorityLevel(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Coordinates3D(BaseModel):
    x: float = Field(0.0, description="X coordinate in meters")
    y: float = Field(0.0, description="Y coordinate in meters")
    z: float = Field(0.0, description="Z coordinate in meters")
    yaw_deg: float = Field(0.0, ge=-180.0, le=180.0, description="Target orientation heading in degrees")


class NavigationParameters(BaseModel):
    target_zone: str = Field(..., min_length=1, max_length=32, description="Identifier for destination zone")
    coordinates: Optional[Coordinates3D] = Field(default_factory=Coordinates3D)
    linear_velocity_max: float = Field(0.5, ge=0.01, le=5.0, description="Max linear velocity in m/s")
    angular_velocity_max: float = Field(1.0, ge=0.01, le=3.14, description="Max angular velocity in rad/s")
    priority: PriorityLevel = Field(PriorityLevel.NORMAL)
    timeout_sec: int = Field(60, ge=1, le=3600, description="Command validity window in seconds")


class DockParameters(BaseModel):
    bay_id: str = Field(..., min_length=1, max_length=32, description="Target docking bay ID")
    approach_speed: float = Field(0.2, ge=0.05, le=1.0, description="Approach velocity in m/s")
    latch_required: bool = Field(True, description="Whether physical mechanical latch is required")


class ChargeParameters(BaseModel):
    station_id: str = Field(..., min_length=1, max_length=32, description="Charging station identifier")
    bay_index: int = Field(1, ge=1, le=64, description="Specific charging pad slot")
    target_soc_pct: float = Field(80.0, ge=10.0, le=100.0, description="Target state of charge percentage")


class ZoneAlertParameters(BaseModel):
    zone_id: str = Field(..., min_length=1, max_length=32, description="Affected zone identifier")
    alert_type: str = Field("OBSTRUCTION", description="Alert categorization (OBSTRUCTION, SPILL, FIRE, HAZARD)")
    severity: PriorityLevel = Field(PriorityLevel.HIGH)
    clearance_required: bool = Field(True)


class CustomParameters(BaseModel):
    action: str = Field(..., min_length=1, max_length=64)
    arguments: Dict[str, Any] = Field(default_factory=dict)


class SecurityHeader(BaseModel):
    auth_type: str = Field("ED25519", description="Cryptographic algorithm: ED25519, HMAC_SHA256, NONE")
    public_key: Optional[str] = Field(None, description="Sender public key hex representation")
    signature: Optional[str] = Field(None, description="Cryptographic digital signature hex")


class RobotCommandMessage(BaseModel):
    """
    Root standard message contract for QR-Link Optical Communication.
    """
    schema_version: str = Field("1.0.0", description="Protocol semantic version")
    sender_id: str = Field(..., min_length=2, max_length=32, description="Unique transmitting robot ID")
    receiver_id: str = Field("BROADCAST", min_length=2, max_length=32, description="Target robot ID or BROADCAST")
    message_id: str = Field(default_factory=lambda: f"MSG-{uuid.uuid4().hex[:8]}")
    sequence_num: int = Field(1, ge=1, description="Monotonic sequence counter per sender")
    timestamp_utc: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC creation timestamp"
    )
    nonce: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        description="Cryptographic one-time nonce to prevent replay attacks"
    )
    command: CommandType
    parameters: Union[
        NavigationParameters,
        DockParameters,
        ChargeParameters,
        ZoneAlertParameters,
        CustomParameters,
    ]
    security: SecurityHeader = Field(default_factory=SecurityHeader)

    def to_canonical_dict(self) -> Dict[str, Any]:
        """
        Produce a deterministic dictionary representation of the payload
        excluding the signature field, used for cryptographic signing and verification.
        """
        data = self.model_dump()
        if "security" in data and "signature" in data["security"]:
            del data["security"]["signature"]
        return data

    def to_compact_json(self) -> str:
        """Serialize into compact JSON without extra whitespace."""
        return self.model_dump_json(exclude_none=True)
