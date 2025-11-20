"""Utilities to compute micrometers-per-pixel and estimate particle sizes.

This module provides two functions:
- `calculate_micrometers_per_pixel` - compute μm/pixel from magnification and image resolution.
- `estimate_particle_size` - compute particle size in μm given pixel count and μm/pixel multiplier.

Defaults are set according to the fixed camera sensor values provided in the request.
"""

from __future__ import annotations

from typing import Dict

# Fixed parameters for the camera sensor (from user-supplied constants)
EFFECTIVE_SENSOR_WIDTH_MM = 23.73
EFFECTIVE_SENSOR_HEIGHT_MM = 15.87
MM_TO_UM = 1000.0  # conversion factor from millimeters to micrometers


def calculate_micrometers_per_pixel(
    M_total: float,
    P_width: int,
    P_height: int,
    effective_sensor_width_mm: float = EFFECTIVE_SENSOR_WIDTH_MM,
    effective_sensor_height_mm: float = EFFECTIVE_SENSOR_HEIGHT_MM,
) -> Dict[str, float]:
    """Calculate micrometers-per-pixel for given imaging setup.

    Args:
        M_total: Total magnification (must be > 0).
        P_width: Image width in pixels (must be > 0).
        P_height: Image height in pixels (must be > 0).
        effective_sensor_width_mm: Effective sensor active width in millimeters (defaults to module constant).
        effective_sensor_height_mm: Effective sensor active height in millimeters (defaults to module constant).

    Returns:
        A dictionary with keys:
          - `width_per_pixel_um`: μm per pixel horizontally (W_pixel)
          - `height_per_pixel_um`: μm per pixel vertically (H_pixel)
          - `average_multiplier_um`: average of the two (useful multiplier)

    Raises:
        ValueError: if any input is non-positive.
    """
    try:
        M_total = float(M_total)
        P_width = int(P_width)
        P_height = int(P_height)
    except Exception:
        raise ValueError("Invalid types for inputs; expected numeric values")

    if M_total <= 0 or P_width <= 0 or P_height <= 0:
        raise ValueError("All inputs must be positive and non-zero")

    # 1) Field of View (FOV) in μm (allow override via parameters)
    fov_width_um = (effective_sensor_width_mm / M_total) * MM_TO_UM
    fov_height_um = (effective_sensor_height_mm / M_total) * MM_TO_UM

    # 2) Pixel size calculation (μm/pixel)
    width_per_pixel_um = fov_width_um / P_width
    height_per_pixel_um = fov_height_um / P_height

    average_multiplier_um = (width_per_pixel_um + height_per_pixel_um) / 2.0

    return {
        "width_per_pixel_um": width_per_pixel_um,
        "height_per_pixel_um": height_per_pixel_um,
        "average_multiplier_um": average_multiplier_um,
    }


def estimate_particle_size(pixel_count: int, um_per_pixel_multiplier: float) -> float:
    """Estimate particle size in micrometers.

    Args:
        pixel_count: Measured particle length in pixels (integer >= 0).
        um_per_pixel_multiplier: μm/pixel multiplier (float > 0), typically
            the `average_multiplier_um` from `calculate_micrometers_per_pixel`.

    Returns:
        Particle size in micrometers as a float.

    Raises:
        ValueError: if inputs are invalid.
    """
    try:
        pixel_count = int(pixel_count)
        um_per_pixel_multiplier = float(um_per_pixel_multiplier)
    except Exception:
        raise ValueError("Invalid types for inputs; expected numeric values")

    if pixel_count < 0:
        raise ValueError("pixel_count must be >= 0")
    if um_per_pixel_multiplier <= 0:
        raise ValueError("um_per_pixel_multiplier must be > 0")

    return float(pixel_count * um_per_pixel_multiplier)


__all__ = [
    "calculate_micrometers_per_pixel",
    "estimate_particle_size",
    "EFFECTIVE_SENSOR_WIDTH_MM",
    "EFFECTIVE_SENSOR_HEIGHT_MM",
]


if __name__ == "__main__":
    # Example usage matching the provided example in the request
    M_total = 2.8
    P_width = 1620
    P_height = 1080
    res = calculate_micrometers_per_pixel(M_total, P_width, P_height)
    print("calculated multipliers:", res)
    print(
        "average (approx):",
        f"{res['average_multiplier_um']:.4f}",
        "μm/pixel (expected approx 5.24)",
    )
    # Example particle size
    pixel_count = 50
    size_um = estimate_particle_size(pixel_count, res["average_multiplier_um"])
    print(f"particle size for {pixel_count} px -> {size_um:.2f} μm")
