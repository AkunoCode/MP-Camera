"""Perimeter calculation (P_μm)"""

from __future__ import annotations

from typing import Union


def calculate_perimeter_um(P_px: Union[float, int], S_um_per_px: float) -> float:
    """Calculate perimeter in micrometers.

    P_um = P_px * S_um_per_px

    Args:
        P_px: perimeter in pixels
        S_um_per_px: micrometers per pixel conversion factor (μm/px)

    Returns:
        Perimeter in μm as float.
    """
    try:
        p_px = float(P_px)
        s = float(S_um_per_px)
    except Exception:
        raise ValueError("Invalid numeric inputs for P_px or S_um_per_px")

    if p_px < 0:
        raise ValueError("P_px must be >= 0")
    if s <= 0:
        raise ValueError("S_um_per_px must be > 0")

    return p_px * s
