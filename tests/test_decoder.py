"""
Unit tests for QR-Link Computer Vision Decoder Module
"""

import pytest
from encoder.qr_encoder import generate_qr_image, QREncoderConfig, QRErrorCorrectionLevel
from decoder.qr_decoder import VisionDecoderEngine, decode_qr_image
from decoder.preprocessor import VisionPreprocessingPipeline


def test_decoder_clean_roundtrip():
    payload = "ROBOT_A:NAVIGATE_TO(ZONE_03)"
    img, _ = generate_qr_image(payload)

    result = decode_qr_image(img)
    assert result.success is True
    assert result.payload == payload
    assert result.latency_ms > 0
    assert result.annotated_image is not None


def test_decoder_preprocessing_stages():
    payload = "TEST_CLAHE_PIPELINE"
    img, _ = generate_qr_image(payload)

    pipeline = VisionPreprocessingPipeline()
    stages = pipeline.process_all_stages(img)

    assert stages.original_bgr.shape[2] == 3
    assert len(stages.grayscale.shape) == 2
    assert stages.otsu_binary.shape == stages.grayscale.shape
    assert stages.adaptive_thresh.shape == stages.grayscale.shape


def test_decoder_invalid_blank_image():
    from PIL import Image
    blank_img = Image.new("RGB", (200, 200), color="white")

    result = decode_qr_image(blank_img)
    assert result.success is False
    assert result.payload is None
    assert "Failed" in result.stage_used
