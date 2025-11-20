import cv2
import numpy as np


def adjust_brightness_contrast(img: np.ndarray, brightness_pct: int = 50, contrast_pct: int = 50) -> np.ndarray:
    """
    Adjust brightness and contrast of an image.

    - `brightness_pct` and `contrast_pct` are 0-100 (slider style).
      50 -> no change, lower -> darker/less contrast, higher -> brighter/more contrast.

    Implementation uses: new = alpha*img + beta
      alpha (contrast) maps from 0.0..2.0 where 1.0 is neutral (contrast_pct/50)
      beta  (brightness) maps from -100..+100 where 0 is neutral ((brightness_pct-50)*2)

    Returns a new uint8 image with same shape.
    """
    if img is None:
        return img

    # Clamp inputs
    b = int(brightness_pct)
    c = int(contrast_pct)

    # Map contrast: 50 -> 1.0, 0 -> 0.0, 100 -> 2.0
    alpha = float(c) / 50.0

    # Map brightness: 50 -> 0, 0 -> -100, 100 -> +100
    beta = float(b - 50) * 2.0

    # Apply the operation
    adjusted = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
    return adjusted
