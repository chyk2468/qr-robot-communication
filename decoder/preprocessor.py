"""
QR-Link Computer Vision Preprocessing Module
Implements multi-stage image enhancement, CLAHE adaptive equalization,
Otsu thresholding, and morphological filtering to maximize QR detection under
harsh lighting, glare, and low contrast.
"""

from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np
from PIL import Image


@dataclass
class PreprocessedImageStages:
    original_bgr: np.ndarray
    grayscale: np.ndarray
    clahe_enhanced: np.ndarray
    otsu_binary: np.ndarray
    adaptive_thresh: np.ndarray


class VisionPreprocessingPipeline:
    """
    Applies sequential computer vision transformations to prepare incoming
    optical frames for high-reliability QR code finder pattern extraction.
    """

    def __init__(self, clip_limit: float = 2.0, tile_grid_size: tuple = (8, 8)):
        self.clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)

    def process_all_stages(self, image: Image.Image) -> PreprocessedImageStages:
        """
        Convert PIL Image into OpenCV format and compute all intermediate stages.
        """
        # Convert PIL to BGR OpenCV format
        rgb_array = np.array(image.convert("RGB"))
        bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

        # 1. Grayscale conversion
        gray = cv2.cvtColor(bgr_array, cv2.COLOR_BGR2GRAY)

        # 2. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe_img = self.clahe.apply(gray)

        # 3. Otsu Automated Global Thresholding
        _, otsu_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 4. Gaussian Adaptive Local Thresholding
        adaptive_thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        return PreprocessedImageStages(
            original_bgr=bgr_array,
            grayscale=gray,
            clahe_enhanced=clahe_img,
            otsu_binary=otsu_bin,
            adaptive_thresh=adaptive_thresh,
        )

    def denoise_and_sharpen(self, gray_image: np.ndarray) -> np.ndarray:
        """
        Apply Gaussian smoothing followed by unsharp masking to enhance blurred edges.
        """
        gaussian = cv2.GaussianBlur(gray_image, (0, 0), 2.0)
        sharpened = cv2.addWeighted(gray_image, 1.5, gaussian, -0.5, 0)
        return sharpened
