"""Color utilities for extracting a dominant/average color from a masked object.

Primary function: `get_color_name(image, mask) -> str`.

Expectations:
- `image` should be a NumPy array in HxWx3 BGR or RGB uint8. The function accepts
  either OpenCV-style BGR (`dtype=uint8`) or RGB; it will detect channels and
  handle both (assumes 3 channels).
- `mask` can be:
  - a boolean or uint8 NumPy array HxW where non-zero/True indicates object pixels,
  - a list/tuple of point dicts or (x,y) tuples describing a polygon (will be rasterized),
  - a sequence of polygons (list of point lists).

The function computes the average RGB of masked pixels, converts to HSV and
returns one of the simplified color names:
  red, orange, yellow, green, blue, purple, pink, brown, black, white, gray

This relies only on NumPy and OpenCV (cv2).
"""

from typing import Any, Iterable, List, Tuple
import numpy as np
import cv2
import pathlib
import colorsys

# Optional heavy dependencies for perceptual matching
try:
    from sklearn.cluster import KMeans
    from colormath.color_objects import sRGBColor, LabColor
    from colormath.color_conversions import convert_color
    from colormath.color_diff import delta_e_cie2000
    import webcolors

    _HAS_PERCEPTUAL = True
except Exception:
    KMeans = None
    sRGBColor = LabColor = convert_color = delta_e_cie2000 = None
    webcolors = None
    _HAS_PERCEPTUAL = False


def _ensure_numpy_image(image: Any) -> np.ndarray:
    if isinstance(image, np.ndarray):
        img = image
    else:
        img = np.array(image)
    if img.dtype != np.uint8:
        try:
            img = img.astype(np.uint8)
        except Exception:
            img = (255 * (img.astype(np.float32) / np.max(img))).astype(np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.ndim == 3 and img.shape[2] == 1:
        img = cv2.cvtColor(img[:, :, 0], cv2.COLOR_GRAY2BGR)
    return img


def _rasterize_mask_from_polygon(
    image_shape: Tuple[int, int], poly: Iterable
) -> np.ndarray:
    h, w = image_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    pts = []
    for p in poly:
        if isinstance(p, dict):
            x = p.get("x") or p.get("X") or p.get("cx") or p.get("cx") or 0
            y = p.get("y") or p.get("Y") or p.get("cy") or p.get("cy") or 0
            try:
                xf = float(x)
                yf = float(y)
            except Exception:
                continue
            # if normalized (0..1), scale
            if 0.0 <= xf <= 1.0 and 0.0 <= yf <= 1.0:
                xf = xf * w
                yf = yf * h
            pts.append([int(round(xf)), int(round(yf))])
        else:
            try:
                x, y = p
                xf = float(x)
                yf = float(y)
                if 0.0 <= xf <= 1.0 and 0.0 <= yf <= 1.0:
                    xf = xf * w
                    yf = yf * h
                pts.append([int(round(xf)), int(round(yf))])
            except Exception:
                continue
    if not pts:
        return mask
    pts_arr = np.array([pts], dtype=np.int32)
    cv2.fillPoly(mask, pts_arr, 255)
    return mask


def _collect_mask(image_shape: Tuple[int, int], mask_input: Any) -> np.ndarray:
    """Return a binary mask HxW (uint8 0/255) from various mask inputs."""
    h, w = image_shape[:2]
    if isinstance(mask_input, np.ndarray):
        if mask_input.dtype != np.uint8:
            m = (mask_input > 0).astype(np.uint8) * 255
        else:
            if mask_input.ndim == 3:
                m = (mask_input.any(axis=2)).astype(np.uint8) * 255
            else:
                m = (mask_input > 0).astype(np.uint8) * 255
        if m.shape != (h, w):
            try:
                m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
            except Exception:
                return np.zeros((h, w), dtype=np.uint8)
        return m
    # polygon or list of polygons
    if isinstance(mask_input, (list, tuple)):
        # detect segmentation flat list
        # if flat numeric list [x,y,x,y,...]
        if mask_input and all(isinstance(v, (int, float)) for v in mask_input):
            # treat as single polygon
            poly = list(zip(mask_input[::2], mask_input[1::2]))
            return _rasterize_mask_from_polygon((h, w), poly)
        # if list of points
        if mask_input and isinstance(mask_input[0], (list, tuple, dict)):
            # single polygon
            if mask_input and not isinstance(mask_input[0][0], (list, tuple, dict)):
                return _rasterize_mask_from_polygon((h, w), mask_input)
            # list of polygons
            out = np.zeros((h, w), dtype=np.uint8)
            for poly in mask_input:
                out = cv2.bitwise_or(out, _rasterize_mask_from_polygon((h, w), poly))
            return out
    if isinstance(mask_input, dict):
        pts = (
            mask_input.get("points")
            or mask_input.get("polygon")
            or mask_input.get("segmentation")
        )
        if pts:
            return _rasterize_mask_from_polygon((h, w), pts)
    return np.zeros((h, w), dtype=np.uint8)


def _closest_css3_name_by_rgb(rgb):
    try:
        if webcolors is None:
            return None
        min_dist = None
        min_name = None
        for hexv, name in webcolors.CSS3_HEX_TO_NAMES.items():
            r2 = int(hexv[1:3], 16)
            g2 = int(hexv[3:5], 16)
            b2 = int(hexv[5:7], 16)
            d = (rgb[0] - r2) ** 2 + (rgb[1] - g2) ** 2 + (rgb[2] - b2) ** 2
            if min_dist is None or d < min_dist:
                min_dist = d
                min_name = name
        return min_name
    except Exception:
        return None


_CSS3_LAB_CACHE = None


def _css3_lab_cache():
    global _CSS3_LAB_CACHE
    if _CSS3_LAB_CACHE is not None:
        return _CSS3_LAB_CACHE
    _CSS3_LAB_CACHE = {}
    if webcolors is None:
        return _CSS3_LAB_CACHE
    for hexv, name in webcolors.CSS3_HEX_TO_NAMES.items():
        try:
            r = int(hexv[1:3], 16)
            g = int(hexv[3:5], 16)
            b = int(hexv[5:7], 16)
            srgb = sRGBColor(r / 255.0, g / 255.0, b / 255.0)
            lab = convert_color(srgb, LabColor)
            _CSS3_LAB_CACHE[name] = (hexv, lab)
        except Exception:
            continue
    return _CSS3_LAB_CACHE


def _map_css3_or_rgb_to_simple(css3_name: str, rgb_arr, score: float = None) -> str:
    """Map a CSS3 name or an RGB array to the simplified color buckets.

    Behavior:
    - If `rgb_arr` is provided, use HSV-based mapping (preferred).
    - If perceptual libs produced a low Delta-E score (small `score`), then
      trust the `css3_name` substring mapping instead of HSV.
    - If `rgb_arr` is not provided, fall back to substring mapping of
      `css3_name`.
    """
    try:
        # If no RGB, rely on css3 substring mapping
        if rgb_arr is None:
            if not css3_name:
                return "unknown"
            ln = css3_name.lower()
            if "red" in ln:
                return "red"
            if "orange" in ln:
                return "orange"
            if "yellow" in ln or "gold" in ln:
                return "yellow"
            if "green" in ln or "lime" in ln:
                return "green"
            if "blue" in ln or "azure" in ln:
                return "blue"
            if "purple" in ln or "violet" in ln or "indigo" in ln:
                return "purple"
            if "pink" in ln or "fuchsia" in ln:
                return "pink"
            if "brown" in ln or "sienna" in ln or "chocolate" in ln:
                return "brown"
            if "black" in ln:
                return "black"
            if "white" in ln:
                return "white"
            if "gray" in ln or "grey" in ln:
                return "gray"
            return "unknown"

        # rgb_arr provided -> prefer HSV mapping
        r, g, b = float(rgb_arr[0]), float(rgb_arr[1]), float(rgb_arr[2])
        rn, gn, bn = r / 255.0, g / 255.0, b / 255.0
        h, s, v = colorsys.rgb_to_hsv(rn, gn, bn)
        # black/white/gray thresholds
        if v < 0.15:
            return "black"
        if s < 0.15:
            if v > 0.85:
                return "white"
            return "gray"

        # If perceptual match exists and score is small (good), trust it
        if _HAS_PERCEPTUAL and score is not None:
            try:
                if float(score) < 18.0:
                    # css3_name likely reliable
                    if css3_name:
                        ln = css3_name.lower()
                        if "red" in ln or "crimson" in ln or "scarlet" in ln:
                            return "red"
                        if "orange" in ln:
                            return "orange"
                        if "yellow" in ln or "gold" in ln:
                            return "yellow"
                        if "green" in ln or "lime" in ln or "olive" in ln:
                            return "green"
                        if "blue" in ln or "navy" in ln or "azure" in ln:
                            return "blue"
                        if "purple" in ln or "violet" in ln or "indigo" in ln:
                            return "purple"
                        if "pink" in ln or "fuchsia" in ln:
                            return "pink"
                        if "brown" in ln or "sienna" in ln or "chocolate" in ln:
                            return "brown"
            except Exception:
                pass

        # HSV fallback mapping (use degrees)
        deg = h * 360.0
        if (deg < 15.0) or (deg >= 345.0):
            return "red"
        if 15.0 <= deg < 45.0:
            return "orange"
        if 45.0 <= deg < 70.0:
            return "yellow"
        if 70.0 <= deg < 160.0:
            return "green"
        if 160.0 <= deg < 260.0:
            return "blue"
        if 260.0 <= deg < 300.0:
            return "purple"
        if 300.0 <= deg < 345.0:
            if v > 0.6:
                return "pink"
            return "purple"
        # as last resort, try css3 substring
        if css3_name:
            ln = css3_name.lower()
            if "red" in ln:
                return "red"
            if "white" in ln:
                return "white"
        return "unknown"
    except Exception:
        return "unknown"


def get_color_name(image: Any, mask: Any) -> str:
    """Return a perceptually-accurate CSS3 color name for the masked object.

    This implementation uses KMeans to find the dominant color (centroid) among
    masked pixels and matches it to the nearest CSS3 color by Delta E (CIE2000)
    when the heavy dependencies are available. Otherwise it falls back to a
    mean-RGB nearest-CSS3 lookup.
    """
    img = _ensure_numpy_image(image)
    h, w = img.shape[:2]
    mask_input = mask
    # If the mask input is a list of points (common), try multiple interpretations
    try_alternatives = (
        isinstance(mask_input, (list, tuple))
        and mask_input
        and isinstance(mask_input[0], (list, tuple, dict, float, int))
    )

    def _compute_for_mask(m):
        sel_local = m.astype(bool)
        if not np.any(sel_local):
            return None
        try:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        except Exception:
            img_rgb = img
        pixels_local = img_rgb[sel_local].astype(float)
        return pixels_local

    best_result = None
    candidates_debug = []

    if try_alternatives:
        # build multiple mask interpretations
        masks = []
        # primary: treat as polygon points (x,y) absolute
        masks.append(_collect_mask((h, w), mask_input))
        # normalized (0..1) variant
        try:
            norm_pts = []
            for p in mask_input:
                if isinstance(p, dict):
                    x = float(p.get("x") or p.get("X") or p.get("cx") or 0)
                    y = float(p.get("y") or p.get("Y") or p.get("cy") or 0)
                else:
                    x = float(p[0])
                    y = float(p[1])
                # if already >1, keep as-is
                if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                    norm_pts.append((x, y))
                else:
                    norm_pts.append((x / w, y / h))
            masks.append(_collect_mask((h, w), norm_pts))
        except Exception:
            pass
        # swapped coords absolute
        try:
            swapped = []
            for p in mask_input:
                if isinstance(p, dict):
                    x = p.get("x") or p.get("X") or 0
                    y = p.get("y") or p.get("Y") or 0
                    swapped.append((y, x))
                else:
                    swapped.append((p[1], p[0]))
            masks.append(_collect_mask((h, w), swapped))
        except Exception:
            pass
        # swapped normalized
        try:
            swapped_norm = []
            for p in mask_input:
                if isinstance(p, dict):
                    x = float(p.get("x") or p.get("X") or 0)
                    y = float(p.get("y") or p.get("Y") or 0)
                else:
                    x = float(p[0])
                    y = float(p[1])
                if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                    swapped_norm.append((y, x))
                else:
                    swapped_norm.append((y / h, x / w))
            masks.append(_collect_mask((h, w), swapped_norm))
        except Exception:
            pass

        # evaluate candidates
        for idx, m in enumerate(masks):
            pixels_local = _compute_for_mask(m)
            if pixels_local is None:
                candidates_debug.append((idx, 0, None, None))
                continue
            # attempt perceptual path
            chosen_name = None
            chosen_score = None
            try:
                n = pixels_local.shape[0]
                sample = pixels_local
                if n > 2000:
                    idxs = np.random.choice(n, 2000, replace=False)
                    sample = pixels_local[idxs]
                if _HAS_PERCEPTUAL and KMeans is not None:
                    # choose k based on data diversity to avoid ConvergenceWarning
                    requested_k = min(3, max(1, int(len(sample) / 500)))
                    try:
                        # count unique colors (round to ints to avoid float noise)
                        uniq = np.unique(np.round(sample).astype(np.int32), axis=0)
                        uniq_n = uniq.shape[0]
                    except Exception:
                        uniq_n = max(1, requested_k)
                    k = min(requested_k, max(1, uniq_n))
                    if uniq_n == 1:
                        # single unique color -> use it directly
                        centroid = uniq[0].astype(float)
                    else:
                        km = KMeans(n_clusters=k, random_state=0).fit(sample)
                        labels, counts = np.unique(km.labels_, return_counts=True)
                        largest = labels[np.argmax(counts)]
                        centroid = km.cluster_centers_[largest]
                    srgb = sRGBColor(
                        centroid[0] / 255.0, centroid[1] / 255.0, centroid[2] / 255.0
                    )
                    lab_cent = convert_color(srgb, LabColor)
                    cache = _css3_lab_cache()
                    best_name = None
                    best_de = float("inf")
                    for name, (hexv, lab) in cache.items():
                        try:
                            de = delta_e_cie2000(lab_cent, lab)
                            if de < best_de:
                                best_de = de
                                best_name = name
                        except Exception:
                            continue
                    chosen_name = best_name
                    chosen_score = float(best_de) if best_de is not None else None
                # fallback: mean RGB
                if chosen_name is None:
                    mean_rgb = pixels_local.mean(axis=0)
                    chosen_name = _closest_css3_name_by_rgb(mean_rgb)
                    # approximate saturation for ranking
                    r, g, b = mean_rgb / 255.0
                    h_s, s_s, v_s = colorsys.rgb_to_hsv(r, g, b)
                    chosen_score = float(s_s)
            except Exception:
                chosen_name = None
                chosen_score = None

            candidates_debug.append(
                (idx, int(pixels_local.shape[0]), chosen_name, chosen_score)
            )
            # choose best: prefer perceptual (delta-E low) else highest saturation
            if best_result is None:
                best_result = (chosen_name, chosen_score, idx)
            else:
                # compare: if both have numeric score (delta-E small is better), pick smaller
                prev_name, prev_score, prev_idx = best_result
                if prev_score is None and chosen_score is not None:
                    best_result = (chosen_name, chosen_score, idx)
                elif prev_score is not None and chosen_score is None:
                    pass
                else:
                    # if scores are comparable in magnitude < 10 we prefer smaller (delta-E), else higher (saturation)
                    try:
                        if _HAS_PERCEPTUAL:
                            # lower is better
                            if chosen_score < prev_score:
                                best_result = (chosen_name, chosen_score, idx)
                        else:
                            # higher saturation better
                            if chosen_score > prev_score:
                                best_result = (chosen_name, chosen_score, idx)
                    except Exception:
                        pass

    else:
        # single path
        bin_mask = _collect_mask((h, w), mask_input)
        pixels = _compute_for_mask(bin_mask)
        if pixels is None:
            try:
                dbg_path = (
                    pathlib.Path(__file__).resolve().parents[1] / "prediction_debug.txt"
                )
                with open(dbg_path, "a", encoding="utf-8") as _dbg:
                    _dbg.write(
                        "COLOR_UTIL_DEBUG: no masked pixels found (single path)\n"
                    )
                    _dbg.write(f"mask_input_type: {type(mask_input)}\n")
            except Exception:
                pass
            return "unknown"
        # proceed with perceptual or mean path as above
        try:
            n = pixels.shape[0]
            sample = pixels
            if n > 2000:
                idxs = np.random.choice(n, 2000, replace=False)
                sample = pixels[idxs]
            if _HAS_PERCEPTUAL and KMeans is not None:
                requested_k = min(3, max(1, int(len(sample) / 500)))
                try:
                    uniq = np.unique(np.round(sample).astype(np.int32), axis=0)
                    uniq_n = uniq.shape[0]
                except Exception:
                    uniq_n = max(1, requested_k)
                k = min(requested_k, max(1, uniq_n))
                if uniq_n == 1:
                    centroid = uniq[0].astype(float)
                else:
                    km = KMeans(n_clusters=k, random_state=0).fit(sample)
                    labels, counts = np.unique(km.labels_, return_counts=True)
                    largest = labels[np.argmax(counts)]
                    centroid = km.cluster_centers_[largest]
                srgb = sRGBColor(
                    centroid[0] / 255.0, centroid[1] / 255.0, centroid[2] / 255.0
                )
                lab_cent = convert_color(srgb, LabColor)
                cache = _css3_lab_cache()
                best_name = None
                best_de = float("inf")
                for name, (hexv, lab) in cache.items():
                    try:
                        de = delta_e_cie2000(lab_cent, lab)
                        if de < best_de:
                            best_de = de
                            best_name = name
                    except Exception:
                        continue
                if best_name:
                    # map to simplified bucket using centroid and delta-E score
                    try:
                        mapped = _map_css3_or_rgb_to_simple(
                            best_name, centroid, best_de
                        )
                        return mapped or best_name
                    except Exception:
                        return best_name
        except Exception:
            pass
        mean_rgb = pixels.mean(axis=0)
        name = _closest_css3_name_by_rgb(mean_rgb)
        if name:
            try:
                return _map_css3_or_rgb_to_simple(name, mean_rgb, None)
            except Exception:
                return name
        try:
            dbg_path = (
                pathlib.Path(__file__).resolve().parents[1] / "prediction_debug.txt"
            )
            with open(dbg_path, "a", encoding="utf-8") as _dbg:
                _dbg.write("COLOR_UTIL_DEBUG: fallback mean-RGB path used\n")
                _dbg.write(f"num_pixels: {pixels.shape[0]}\n")
                _dbg.write(f"mean_rgb: {mean_rgb.tolist()}\n")
                _dbg.write(f"has_perceptual_libs: {_HAS_PERCEPTUAL}\n")
        except Exception:
            pass
        return "unknown"

    # after evaluating candidates, pick best_result
    try:
        # log candidates
        dbg_path = pathlib.Path(__file__).resolve().parents[1] / "prediction_debug.txt"
        with open(dbg_path, "a", encoding="utf-8") as _dbg:
            _dbg.write("COLOR_UTIL_CANDIDATES:\n")
            for c in candidates_debug:
                _dbg.write(
                    f"candidate_idx={c[0]} num_pixels={c[1]} name={c[2]} score={c[3]}\n"
                )
    except Exception:
        pass

    if best_result is None:
        return "unknown"
    selected_name, selected_score, selected_idx = best_result
    # compute a representative RGB for the selected candidate (mean of masked pixels)
    try:
        sel_mask = masks[selected_idx]
        sel_bool = sel_mask.astype(bool)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        sel_pixels = img_rgb[sel_bool].astype(float)
        if sel_pixels.size:
            rep_rgb = sel_pixels.mean(axis=0)
        else:
            rep_rgb = None
    except Exception:
        rep_rgb = None

    mapped = _map_css3_or_rgb_to_simple(selected_name, rep_rgb, selected_score)
    # log selection and mapping
    try:
        dbg_path = pathlib.Path(__file__).resolve().parents[1] / "prediction_debug.txt"
        with open(dbg_path, "a", encoding="utf-8") as _dbg:
            _dbg.write("COLOR_UTIL_SELECTION:\n")
            _dbg.write(
                f"selected_css3={selected_name} score={selected_score} idx={selected_idx}\n"
            )
            _dbg.write(
                f"rep_rgb={None if rep_rgb is None else rep_rgb.tolist()} mapped={mapped}\n"
            )
    except Exception:
        pass

    return mapped or "unknown"
