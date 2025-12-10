"""
Unit tests for QR-Link Optical Encoder Module
"""

import pytest
from PIL import Image
from encoder.qr_encoder import (
    QRErrorCorrectionLevel,
    QREncoderConfig,
    generate_qr_image,
    generate_qr_bytes,
    generate_qr_base64,
)


def test_qr_encoder_default_generation():
    text = "TEST_ROBOT_COMMAND"
    img, telemetry = generate_qr_image(text)

    assert isinstance(img, Image.Image)
    assert img.width > 50
    assert img.height > 50
    assert telemetry.char_length == len(text)
    assert telemetry.byte_length == len(text.encode("utf-8"))
    assert telemetry.error_correction == QRErrorCorrectionLevel.MEDIUM.value


def test_qr_encoder_custom_error_correction():
    text = "HIGH_RESILIENCE_PAYLOAD"
    config = QREncoderConfig(
        error_correction=QRErrorCorrectionLevel.HIGH,
        box_size=12,
        border=5,
        fill_color="#1E293B",
        back_color="#F8FAFC",
    )
    img, telemetry = generate_qr_image(text, config)

    assert telemetry.error_recovery_pct == "30%"
    assert telemetry.error_correction == QRErrorCorrectionLevel.HIGH.value


def test_qr_encoder_bytes_and_base64():
    text = "MOVE_FORWARD;SPEED=0.5"
    png_bytes, tel1 = generate_qr_bytes(text)
    assert len(png_bytes) > 0
    assert png_bytes.startswith(b"\x89PNG")

    b64_uri, tel2 = generate_qr_base64(text)
    assert b64_uri.startswith("data:image/png;base64,")
