"""Circularity calculation (C)"""

from __future__ import annotations

import math
from typing import Union


def calculate_circularity(
    A_um2: Union[float, int], P_um: Union[float, int], S_um_per_px: float
) -> float:
    """Calculate circularity: C = (4 * pi * A) / P^2

    Args:
        A_um2: area in μm²
        P_um: perimeter in μm
        S_um_per_px: micrometers per pixel conversion factor (μm/px) - included in signature
            for interface consistency; not used when inputs are already in μm.

    Returns:
        Circularity as float (0..1 for normal shapes). Raises ValueError on invalid inputs.
    """
    try:
        a = float(A_um2)
        p = float(P_um)
        _ = float(S_um_per_px)
    except Exception:
        raise ValueError("Invalid numeric inputs for A_um2, P_um or S_um_per_px")

    if a < 0:
        raise ValueError("A_um2 must be >= 0")
    if p <= 0:
        raise ValueError("P_um must be > 0")

    return (4.0 * math.pi * a) / (p**2)
