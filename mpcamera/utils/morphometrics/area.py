"""Area calculation (A_μm²)"""

from __future__ import annotations

from typing import Union


def calculate_area_um2(A_px: Union[float, int], S_um_per_px: float) -> float:
    """Calculate area in square micrometers.

    A_um2 = A_px * (S_um_per_px ** 2)

    Args:
        A_px: area in pixels (px²)
        S_um_per_px: micrometers per pixel conversion factor (μm/px)

    Returns:
        Area in μm² as float.
    """
    try:
        a_px = float(A_px)
        s = float(S_um_per_px)
    except Exception:
        raise ValueError("Invalid numeric inputs for A_px or S_um_per_px")

    if a_px < 0:
        raise ValueError("A_px must be >= 0")
    if s <= 0:
        raise ValueError("S_um_per_px must be > 0")

    return a_px * (s**2)
