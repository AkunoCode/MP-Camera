"""Equivalent circular diameter (D_eq)"""

from __future__ import annotations

import math
from typing import Union


def calculate_equivalent_circular_diameter(
    A_um2: Union[float, int], S_um_per_px: float
) -> float:
    """Calculate equivalent circular diameter from area in μm².

    D_eq = 2 * sqrt(A_um2 / pi)

    Note: `S_um_per_px` is required by the package interface but not used
    when an area in μm² is provided (it is used upstream to compute A_um2).

    Args:
        A_um2: area in square micrometers
        S_um_per_px: micrometers per pixel conversion factor (μm/px)

    Returns:
        Equivalent circular diameter in μm as float.
    """
    try:
        a = float(A_um2)
        _ = float(S_um_per_px)
    except Exception:
        raise ValueError("Invalid numeric inputs for A_um2 or S_um_per_px")

    if a < 0:
        raise ValueError("A_um2 must be >= 0")

    return 2.0 * math.sqrt(a / math.pi)
