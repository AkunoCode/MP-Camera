"""Minor axis length calculation (L_minor in μm)"""

from __future__ import annotations

from typing import Union


def calculate_minor_axis_um(L_minor_px: Union[float, int], S_um_per_px: float) -> float:
    """Calculate minor axis length in micrometers.

    Args:
        L_minor_px: minor axis length in pixels
        S_um_per_px: micrometers per pixel conversion factor (μm/px)

    Returns:
        Minor axis length in μm as float.
    """
    try:
        lm_px = float(L_minor_px)
        s = float(S_um_per_px)
    except Exception:
        raise ValueError("Invalid numeric inputs for L_minor_px or S_um_per_px")

    if lm_px < 0:
        raise ValueError("L_minor_px must be >= 0")
    if s <= 0:
        raise ValueError("S_um_per_px must be > 0")

    return lm_px * s
