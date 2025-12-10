"""
QR-Link Optical Encoder Module
Handles high-density 2D matrix synthesis with configurable error correction,
custom styling, and detailed encoding telemetry.
"""

import io
import base64
from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Optional
import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
from PIL import Image


class QRErrorCorrectionLevel(str, Enum):
    LOW = "L (7% recovery)"
    MEDIUM = "M (15% recovery)"
    QUARTILE = "Q (25% recovery)"
    HIGH = "H (30% recovery)"

    def to_qrcode_constant(self) -> int:
        mapping = {
            QRErrorCorrectionLevel.LOW: ERROR_CORRECT_L,
            QRErrorCorrectionLevel.MEDIUM: ERROR_CORRECT_M,
            QRErrorCorrectionLevel.QUARTILE: ERROR_CORRECT_Q,
            QRErrorCorrectionLevel.HIGH: ERROR_CORRECT_H,
        }
        return mapping[self]


@dataclass
class QREncoderConfig:
    error_correction: QRErrorCorrectionLevel = QRErrorCorrectionLevel.MEDIUM
    box_size: int = 10
    border: int = 4
    fill_color: str = "#000000"
    back_color: str = "#FFFFFF"


@dataclass
class QRCodeTelemetry:
    byte_length: int
    char_length: int
    matrix_version: Optional[int]
    error_correction: str
    dimensions_px: Tuple[int, int]
    error_recovery_pct: str


def generate_qr_image(
    data: str,
    config: Optional[QREncoderConfig] = None,
) -> Tuple[Image.Image, QRCodeTelemetry]:
    """
    Generate a high-contrast 2D QR matrix image from string payload.
    
    Args:
        data: The UTF-8 string payload to encode.
        config: Encoder styling and error correction configuration.
        
    Returns:
        Tuple containing the PIL RGB image and encoding telemetry metadata.
    """
    if config is None:
        config = QREncoderConfig()

    qr = qrcode.QRCode(
        version=None,  # Auto-determine matrix version
        error_correction=config.error_correction.to_qrcode_constant(),
        box_size=config.box_size,
        border=config.border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color=config.fill_color,
        back_color=config.back_color,
    ).convert("RGB")

    recovery_map = {
        QRErrorCorrectionLevel.LOW: "7%",
        QRErrorCorrectionLevel.MEDIUM: "15%",
        QRErrorCorrectionLevel.QUARTILE: "25%",
        QRErrorCorrectionLevel.HIGH: "30%",
    }

    telemetry = QRCodeTelemetry(
        byte_length=len(data.encode("utf-8")),
        char_length=len(data),
        matrix_version=qr.version,
        error_correction=config.error_correction.value,
        dimensions_px=(img.width, img.height),
        error_recovery_pct=recovery_map.get(config.error_correction, "15%"),
    )

    return img, telemetry


def generate_qr_bytes(
    data: str,
    config: Optional[QREncoderConfig] = None,
    image_format: str = "PNG",
) -> Tuple[bytes, QRCodeTelemetry]:
    """
    Generate raw byte buffer of the rendered QR code image.
    """
    img, telemetry = generate_qr_image(data, config)
    buffer = io.BytesIO()
    img.save(buffer, format=image_format)
    return buffer.getvalue(), telemetry


def generate_qr_base64(
    data: str,
    config: Optional[QREncoderConfig] = None,
) -> Tuple[str, QRCodeTelemetry]:
    """
    Generate a base64 Data URI for direct web embedding.
    """
    png_bytes, telemetry = generate_qr_bytes(data, config, image_format="PNG")
    b64_encoded = base64.b64encode(png_bytes).decode("ascii")
    data_uri = f"data:image/png;base64,{b64_encoded}"
    return data_uri, telemetry
