"""Aspect ratio calculation (R_aspect)"""

from __future__ import annotations

from typing import Union


def calculate_aspect_ratio(
    L_major_um: Union[float, int], L_minor_um: Union[float, int], S_um_per_px: float
) -> float:
    """Calculate aspect ratio L_major / L_minor.

    Note: S_um_per_px is part of the common interface but not required when
    both inputs are already in μm.

    Args:
        L_major_um: major axis length in μm
        L_minor_um: minor axis length in μm
        S_um_per_px: micrometers per pixel conversion factor (μm/px)

    Returns:
        Aspect ratio as float. Raises ValueError on invalid inputs.
    """
    try:
        Lm = float(L_major_um)
        lm = float(L_minor_um)
        _ = float(S_um_per_px)
    except Exception:
        raise ValueError(
            "Invalid numeric inputs for L_major_um, L_minor_um, or S_um_per_px"
        )

    if Lm < 0 or lm <= 0:
        raise ValueError("L_major_um must be >= 0 and L_minor_um must be > 0")

    return Lm / lm if lm != 0 else float("inf")
