"""
QR-Link Multi-Pass Computer Vision Decoder Module
Uses OpenCV QRCodeDetector with multi-pass fallback cascades, bounding box
quadrilateral extraction, and timing telemetry.
"""

import time
from dataclasses import dataclass
from typing import Optional, Tuple, List
import cv2
import numpy as np
from PIL import Image

from .preprocessor import VisionPreprocessingPipeline, PreprocessedImageStages


@dataclass
class QRDecoderResult:
    success: bool
    payload: Optional[str] = None
    bounding_box: Optional[np.ndarray] = None
    annotated_image: Optional[Image.Image] = None
    stage_used: str = "None"
    latency_ms: float = 0.0
    error_message: Optional[str] = None


class VisionDecoderEngine:
    """
    Multi-pass optical decoder with automatic fallback cascade across
    color, grayscale, CLAHE, Otsu binarization, and adaptive thresholding.
    """

    def __init__(self):
        self.detector = cv2.QRCodeDetector()
        self.pipeline = VisionPreprocessingPipeline()

    def decode(self, image: Image.Image) -> QRDecoderResult:
        """
        Execute multi-pass decoding on an input PIL image.
        """
        start_time = time.perf_counter()
        stages: PreprocessedImageStages = self.pipeline.process_all_stages(image)

        # Cascading candidate passes in order of speed and clarity
        candidates = [
            ("Standard RGB/BGR", stages.original_bgr),
            ("Grayscale", stages.grayscale),
            ("CLAHE Contrast Equalization", stages.clahe_enhanced),
            ("Otsu Automated Binarization", stages.otsu_binary),
            ("Adaptive Gaussian Thresholding", stages.adaptive_thresh),
        ]

        decoded_text = ""
        points = None
        successful_stage = "None"

        for stage_name, candidate_img in candidates:
            try:
                data, pts, _ = self.detector.detectAndDecode(candidate_img)
                if data:
                    decoded_text = data
                    points = pts
                    successful_stage = stage_name
                    break
                elif pts is not None and len(pts) > 0 and not decoded_text:
                    # Finder patterns found but decode failed; retain points for debugging
                    points = pts
            except Exception:
                continue

        # If still failed, try unsharp mask pass
        if not decoded_text:
            sharpened = self.pipeline.denoise_and_sharpen(stages.grayscale)
            try:
                data, pts, _ = self.detector.detectAndDecode(sharpened)
                if data:
                    decoded_text = data
                    points = pts
                    successful_stage = "Sharpened Denoised"
            except Exception:
                pass

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if decoded_text:
            annotated_pil = self._draw_annotations(stages.original_bgr, points, decoded_text)
            return QRDecoderResult(
                success=True,
                payload=decoded_text,
                bounding_box=points,
                annotated_image=annotated_pil,
                stage_used=successful_stage,
                latency_ms=round(latency_ms, 2),
            )
        else:
            annotated_pil = self._draw_failed_annotations(stages.original_bgr, points)
            return QRDecoderResult(
                success=False,
                payload=None,
                bounding_box=points,
                annotated_image=annotated_pil,
                stage_used="Failed across all 6 passes",
                latency_ms=round(latency_ms, 2),
                error_message="No valid QR code finder patterns detected in image frame.",
            )

    def _draw_annotations(
        self,
        bgr_img: np.ndarray,
        points: Optional[np.ndarray],
        text_preview: str,
    ) -> Image.Image:
        """
        Draw high-visibility bounding polygon and status badge over the image.
        """
        annotated = bgr_img.copy()

        if points is not None and len(points) > 0:
            pts = points.astype(int)
            if len(pts.shape) == 3:
                pts = pts.reshape((-1, 1, 2))

            # Draw green bounding polygon
            cv2.polylines(annotated, [pts], isClosed=True, color=(34, 197, 94), thickness=3)

            # Draw corner anchor points
            for pt in pts.reshape(-1, 2):
                cv2.circle(annotated, (int(pt[0]), int(pt[1])), 6, (99, 102, 241), -1)

            # Top-left anchor for label
            min_x = int(np.min(pts[:, :, 0]))
            min_y = int(np.max([np.min(pts[:, :, 1]) - 12, 24]))

            label = "QR-LINK DETECTED"
            cv2.putText(
                annotated,
                label,
                (min_x, min_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (34, 197, 94),
                2,
                cv2.LINE_AA,
            )

        # Convert back to PIL RGB
        rgb_annotated = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_annotated)

    def _draw_failed_annotations(
        self,
        bgr_img: np.ndarray,
        points: Optional[np.ndarray],
    ) -> Image.Image:
        annotated = bgr_img.copy()
        if points is not None and len(points) > 0:
            pts = points.astype(int)
            if len(pts.shape) == 3:
                pts = pts.reshape((-1, 1, 2))
            cv2.polylines(annotated, [pts], isClosed=True, color=(239, 68, 68), thickness=2)

        rgb_annotated = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_annotated)


def decode_qr_image(image: Image.Image) -> QRDecoderResult:
    """Convenience function to decode a single image."""
    engine = VisionDecoderEngine()
    return engine.decode(image)
