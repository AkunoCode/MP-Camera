"""Major axis length calculation (L_major in μm)"""

from __future__ import annotations

from typing import Union


def calculate_major_axis_um(L_major_px: Union[float, int], S_um_per_px: float) -> float:
    """Calculate major axis length in micrometers.

    Args:
        L_major_px: major axis length in pixels
        S_um_per_px: micrometers per pixel conversion factor (μm/px)

    Returns:
        Major axis length in μm as float.
    """
    try:
        lm_px = float(L_major_px)
        s = float(S_um_per_px)
    except Exception:
        raise ValueError("Invalid numeric inputs for L_major_px or S_um_per_px")

    if lm_px < 0:
        raise ValueError("L_major_px must be >= 0")
    if s <= 0:
        raise ValueError("S_um_per_px must be > 0")

    return lm_px * s
