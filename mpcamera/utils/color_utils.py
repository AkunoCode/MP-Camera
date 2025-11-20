"""
Color utilities for extracting a dominant/average color from a masked object.
Returns simplified names: red, orange, yellow, green, blue, purple, pink, brown, black, white, gray.
"""

import cv2
import numpy as np
import colorsys
from typing import Any, Union, List, Dict, Tuple

# Optional: Use KMeans for better dominant color extraction if available
try:
    from sklearn.cluster import KMeans

    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


def get_color_name(image: np.ndarray, mask: Any) -> str:
    """
    Determines the simplified color name of the object defined by the mask.

    Args:
        image: BGR image (uint8)
        mask: Can be a boolean mask, a list of points [{'x':1, 'y':2}, ...],
              or a list of lists (polygons).
    """
    # 1. Ensure Image is BGR uint8
    image = _ensure_image_format(image)
    h, w = image.shape[:2]

    # 2. Create Binary Mask (uint8)
    binary_mask = _parse_mask_to_uint8(mask, (h, w))

    # 3. Extract Object Pixels
    # Get all pixels where mask is white
    object_pixels = image[binary_mask == 255]

    if object_pixels.size == 0:
        return "unknown"

    # 4. Calculate Dominant RGB
    dominant_bgr = _get_dominant_color(object_pixels)

    # 5. Convert to HSV for naming
    # OpenCV uses H: 0-179, S: 0-255, V: 0-255
    # We convert to standard 0-1 float for colorsys logic ease, or use custom logic
    b, g, r = dominant_bgr
    dominant_rgb = (r, g, b)

    return _map_rgb_to_name(dominant_rgb)


def _ensure_image_format(image: Any) -> np.ndarray:
    """Ensures image is HxWx3 BGR uint8."""
    img = np.array(image)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    return img.astype(np.uint8)


def _parse_mask_to_uint8(mask_input: Any, shape: Tuple[int, int]) -> np.ndarray:
    """Converts various mask inputs into a standardized uint8 0/255 mask."""
    h, w = shape
    canvas = np.zeros((h, w), dtype=np.uint8)

    # Case A: Input is already a numpy array (boolean or int)
    if isinstance(mask_input, np.ndarray):
        if mask_input.shape[:2] != (h, w):
            mask_input = cv2.resize(mask_input, (w, h), interpolation=cv2.INTER_NEAREST)

        if mask_input.dtype == bool:
            return mask_input.astype(np.uint8) * 255
        else:
            # Ensure binary
            _, thresh = cv2.threshold(mask_input, 1, 255, cv2.THRESH_BINARY)
            return thresh.astype(np.uint8)

    # Case B: Input is a list/dict of points (Polygon)
    # Example: [{'x': 10, 'y': 10}, ...] or [[10,10], [20,20]]
    points = []

    # Helper to extract list of points
    raw_poly = mask_input

    # If it's a list of polygons (list of lists), just take the first (largest) or merge
    if isinstance(mask_input, list) and len(mask_input) > 0:
        # Check if it's a list of points or list of polygons
        first_item = mask_input[0]
        if (
            isinstance(first_item, list)
            and len(first_item) > 0
            and isinstance(first_item[0], (list, dict))
        ):
            # It's a list of polygons, flatten/draw all
            for poly in mask_input:
                sub_mask = _parse_mask_to_uint8(poly, shape)
                canvas = cv2.bitwise_or(canvas, sub_mask)
            return canvas

    # Flatten points
    if isinstance(mask_input, list):
        for p in mask_input:
            x, y = 0, 0
            if isinstance(p, dict):
                x = p.get("x", 0)
                y = p.get("y", 0)
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                x, y = p[0], p[1]

            # Check if normalized (0.0-1.0)
            if isinstance(x, float) and x <= 1.0 and isinstance(y, float) and y <= 1.0:
                x = int(x * w)
                y = int(y * h)
            else:
                x, y = int(x), int(y)

            points.append([x, y])

    if points:
        pts_array = np.array([points], dtype=np.int32)
        cv2.fillPoly(canvas, pts_array, 255)

    return canvas


def _get_dominant_color(pixels: np.ndarray) -> Tuple[float, float, float]:
    """
    Returns (B, G, R) of the dominant color.
    Uses KMeans if sklearn is available (slower, more accurate), else Mean (fast).
    """
    # Optimize: If too many pixels, sample them to speed up
    if len(pixels) > 2000:
        indices = np.random.choice(len(pixels), 2000, replace=False)
        pixels = pixels[indices]

    if _HAS_SKLEARN and len(pixels) >= 5:
        try:
            # Find 3 clusters, pick the largest
            kmeans = KMeans(n_clusters=3, n_init=5, random_state=42)
            kmeans.fit(pixels)

            # Count labels to find most frequent cluster
            unique, counts = np.unique(kmeans.labels_, return_counts=True)
            dominant_index = unique[np.argmax(counts)]
            return kmeans.cluster_centers_[dominant_index]
        except Exception:
            # Fallback to mean on error
            pass

    # Fallback: simple average
    return np.mean(pixels, axis=0)


def _map_rgb_to_name(rgb: Tuple[float, float, float]) -> str:
    """
    Maps an RGB tuple (0-255) to a simplified color name using HSV space.
    """
    r, g, b = rgb

    # Convert to 0-1 range for colorsys
    r_norm, g_norm, b_norm = r / 255.0, g / 255.0, b / 255.0

    # Convert to HSV
    h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)

    # H is 0-1, convert to degrees 0-360
    h_deg = h * 360

    # --- 1. Achromatic Check (Black, White, Gray) ---
    # Low Value = Black
    if v < 0.15:
        return "Black"

    # Low Saturation = White or Gray
    if s < 0.15:
        if v > 0.80:
            return "White"
        else:
            return "Gray"

    # --- 2. Chromatic Check (Hues) ---
    # Note: Red wraps around 0/360
    if (h_deg >= 0 and h_deg < 15) or (h_deg >= 345 and h_deg <= 360):
        return "Red"
    elif 15 <= h_deg < 45:
        # Check for Brown vs Orange/Yellow
        # Brown is essentially dark orange/yellow
        if v < 0.50:
            return "Brown"
        return "Orange"
    elif 45 <= h_deg < 75:
        return "Yellow"
    elif 75 <= h_deg < 165:
        return "Green"
    elif 165 <= h_deg < 260:
        return "Blue"
    elif 260 <= h_deg < 300:
        return "Purple"
    elif 300 <= h_deg < 345:
        return "Pink"

    return "Unknown"
