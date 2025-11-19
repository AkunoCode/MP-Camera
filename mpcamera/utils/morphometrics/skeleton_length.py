"""Skeleton length calculation (L_skeleton in μm)"""

from __future__ import annotations

from typing import Union


def calculate_skeleton_length_um(
    N_skeleton_px: Union[float, int], S_um_per_px: float
) -> float:
    """Calculate skeleton (central spine) length in micrometers.

    Args:
        N_skeleton_px: number of skeleton pixels
        S_um_per_px: micrometers per pixel conversion factor (μm/px)

    Returns:
        Skeleton length in μm as float.
    """
    try:
        n_px = float(N_skeleton_px)
        s = float(S_um_per_px)
    except Exception:
        raise ValueError("Invalid numeric inputs for N_skeleton_px or S_um_per_px")

    if n_px < 0:
        raise ValueError("N_skeleton_px must be >= 0")
    if s <= 0:
        raise ValueError("S_um_per_px must be > 0")

    return n_px * s
