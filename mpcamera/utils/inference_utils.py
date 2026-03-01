from typing import List, Dict, Any, Optional
from math import isnan

from mpcamera.utils.prediction_utils import extract_points_from_prediction
from mpcamera.utils.camera_utils import color_for_label


_CLASS_KEYS = ["sheet", "fragment", "fiber", "bead", "foam", "film"]


def _safe_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        if isnan(f):
            return None
        return f
    except Exception:
        return None


def _pred_confidence(pred: Dict[str, Any]) -> Optional[float]:
    for k in ("confidence", "score", "confidence_score"):
        f = _safe_float(pred.get(k))
        if f is not None:
            return f
    return None


def _pred_to_xyxy(pred: Dict[str, Any]) -> Optional[List[float]]:
    # Explicit xyxy keys
    x1 = _safe_float(pred.get("x1"))
    y1 = _safe_float(pred.get("y1"))
    x2 = _safe_float(pred.get("x2"))
    y2 = _safe_float(pred.get("y2"))
    if None not in (x1, y1, x2, y2) and x2 > x1 and y2 > y1:
        return [x1, y1, x2, y2]

    # left/top/right/bottom variants
    left = _safe_float(pred.get("left"))
    top = _safe_float(pred.get("top"))
    right = _safe_float(pred.get("right"))
    bottom = _safe_float(pred.get("bottom"))
    if None not in (left, top, right, bottom) and right > left and bottom > top:
        return [left, top, right, bottom]

    # bbox common format [x, y, w, h]
    bbox = pred.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        bx = _safe_float(bbox[0])
        by = _safe_float(bbox[1])
        bw = _safe_float(bbox[2])
        bh = _safe_float(bbox[3])
        if None not in (bx, by, bw, bh) and bw > 0 and bh > 0:
            return [bx, by, bx + bw, by + bh]

    # center-x/y + width/height
    cx = _safe_float(pred.get("x"))
    cy = _safe_float(pred.get("y"))
    w = _safe_float(pred.get("width"))
    h = _safe_float(pred.get("height"))
    if None not in (cx, cy, w, h) and w > 0 and h > 0:
        return [cx - (w / 2.0), cy - (h / 2.0), cx + (w / 2.0), cy + (h / 2.0)]

    # fallback from polygon points
    try:
        pts = extract_points_from_prediction(pred) or []
        if pts:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            x1p = min(xs)
            y1p = min(ys)
            x2p = max(xs)
            y2p = max(ys)
            if x2p > x1p and y2p > y1p:
                return [x1p, y1p, x2p, y2p]
    except Exception:
        pass

    return None


def _iou_xyxy(a: List[float], b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih

    a_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = a_area + b_area - inter
    if union <= 0:
        return 0.0
    return inter / union


def _looks_like_prediction_dict(d: Dict[str, Any]) -> bool:
    # Deliberately avoid considering only x/y keys to prevent filtering polygon points.
    for k in (
        "class",
        "label",
        "confidence",
        "score",
        "bbox",
        "points",
        "segmentation",
        "mask",
        "width",
        "height",
    ):
        if k in d:
            return True
    return False


def _filter_prediction_list(
    preds: List[Dict[str, Any]],
    confidence_threshold: Optional[float],
    iou_threshold: Optional[float],
) -> List[Dict[str, Any]]:
    if not preds:
        return preds

    conf_t = _safe_float(confidence_threshold)
    iou_t = _safe_float(iou_threshold)
    if iou_t is not None and (iou_t < 0.0 or iou_t > 1.0):
        iou_t = None

    kept: List[Dict[str, Any]] = []
    boxed_meta: List[Dict[str, Any]] = []

    for pred in preds:
        if not isinstance(pred, dict):
            continue
        score = _pred_confidence(pred)
        if conf_t is not None and score is not None and score < conf_t:
            continue
        local_idx = len(kept)
        kept.append(pred)
        box = _pred_to_xyxy(pred)
        if box is not None:
            boxed_meta.append(
                {
                    "local_idx": local_idx,
                    "score": score if score is not None else 1.0,
                    "box": box,
                }
            )

    if iou_t is None or len(boxed_meta) <= 1:
        return kept

    # Greedy NMS on available boxes
    order = sorted(
        range(len(boxed_meta)),
        key=lambda i: float(boxed_meta[i]["score"]),
        reverse=True,
    )
    keep_boxed_positions: List[int] = []

    while order:
        cur = order.pop(0)
        keep_boxed_positions.append(cur)
        cur_box = boxed_meta[cur]["box"]

        survivors = []
        for j in order:
            other_box = boxed_meta[j]["box"]
            if _iou_xyxy(cur_box, other_box) <= iou_t:
                survivors.append(j)
        order = survivors

    keep_local_indices = {
        boxed_meta[pos]["local_idx"] for pos in keep_boxed_positions
    }
    # Always retain detections that had no valid box for NMS.
    for i, pred in enumerate(kept):
        if _pred_to_xyxy(pred) is None:
            keep_local_indices.add(i)

    return [p for i, p in enumerate(kept) if i in keep_local_indices]


def apply_confidence_iou_filters(
    result: Any,
    confidence_threshold: Optional[float] = None,
    iou_threshold: Optional[float] = None,
) -> Any:
    """Mutate `result` in-place to enforce confidence and IoU filtering.

    This acts as a backend-agnostic post-filter so sliders behave consistently
    across local and cloud models, including payloads where backend-level IoU
    controls are unavailable.
    """

    def _walk(obj: Any):
        try:
            if isinstance(obj, dict):
                for k, v in list(obj.items()):
                    if isinstance(v, list) and v and all(
                        isinstance(it, dict) for it in v
                    ):
                        if any(_looks_like_prediction_dict(it) for it in v):
                            obj[k] = _filter_prediction_list(
                                v,
                                confidence_threshold=confidence_threshold,
                                iou_threshold=iou_threshold,
                            )
                        else:
                            for it in v:
                                _walk(it)
                    elif isinstance(v, (dict, list)):
                        _walk(v)
            elif isinstance(obj, list):
                for it in obj:
                    if isinstance(it, (dict, list)):
                        _walk(it)
        except Exception:
            return

    _walk(result)
    return result


def _normalize_label(label: Optional[str]) -> str:
    if label is None:
        return ""
    return str(label).strip()


def _collect_pred_dicts(obj: Any) -> List[Dict[str, Any]]:
    """Recursively search `obj` for lists of dict prediction items.

    Returns the first-level list of dicts found, or flattens nested lists.
    """
    out: List[Dict[str, Any]] = []
    try:
        if obj is None:
            return out
        if isinstance(obj, list):
            # if list contains dicts, determine if they look like prediction items
            if obj and isinstance(obj[0], dict):

                def looks_like_pred(d: Dict[str, Any]) -> bool:
                    # common keys in prediction dicts
                    for k in (
                        "class",
                        "label",
                        "confidence",
                        "points",
                        "bbox",
                        "x",
                        "y",
                    ):
                        if k in d:
                            return True
                    return False

                # if any element looks like a prediction, return all dict elements
                if any(isinstance(it, dict) and looks_like_pred(it) for it in obj):
                    return [it for it in obj if isinstance(it, dict)]
                # otherwise recurse into each dict element to find nested prediction lists
                for el in obj:
                    out.extend(_collect_pred_dicts(el))
                return out
            # otherwise recurse into elements
            for el in obj:
                out.extend(_collect_pred_dicts(el))
            return out
        if isinstance(obj, dict):
            # check common wrapper keys first
            for k in ("predictions", "preds", "outputs", "results", "objects", "data"):
                v = obj.get(k)
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return [it for it in v if isinstance(it, dict)]
            # otherwise search values
            for v in obj.values():
                out.extend(_collect_pred_dicts(v))
            return out
    except Exception:
        return out
    return out


def parse_result_to_preds(result: Any) -> List[Dict[str, Any]]:
    """Turn raw inference result into a flat list of prediction dicts.

    Each returned item contains: 'label', 'score' (float|None), 'color' (hex),
    optional 'points' and 'size' (None by default).
    """
    flat = _collect_pred_dicts(result)

    out = []
    for p in flat:
        try:
            if not isinstance(p, dict):
                continue
            label = (
                p.get("class")
                or p.get("label")
                or p.get("predicted_class")
                or p.get("name")
                or str(p.get("id", ""))
            )
            score = None
            for k in ("confidence", "score", "confidence_score"):
                v = p.get(k)
                if v is not None:
                    try:
                        score = float(v)
                        break
                    except Exception:
                        score = None
            # try points
            pts = []
            try:
                pts = extract_points_from_prediction(p) or []
            except Exception:
                pts = []

            label_text = _normalize_label(label)
            color_q = color_for_label(label_text)
            # QColor.name() returns '#RRGGBB'
            color_hex = color_q.name() if hasattr(color_q, "name") else str(color_q)

            out.append(
                {
                    "label": label_text,
                    "score": score,
                    "points": pts,
                    "color": color_hex,
                    "size": None,
                    "raw": p,
                }
            )
        except Exception:
            continue

    return out


def compute_aggregates(preds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute totals, average confidence, and counts per class.

    Returns a dict containing: total, ave_confidence, counts (mapping).
    """
    total = len(preds)
    confidences = [p.get("score") for p in preds if p.get("score") is not None]
    ave_conf = None
    min_conf = None
    max_conf = None
    try:
        if confidences:
            ave_conf = sum(confidences) / len(confidences)
            try:
                min_conf = min(confidences)
            except Exception:
                min_conf = None
            try:
                max_conf = max(confidences)
            except Exception:
                max_conf = None
    except Exception:
        ave_conf = None
        min_conf = None
        max_conf = None

    counts = {k: 0 for k in _CLASS_KEYS}
    try:
        for p in preds:
            lab = p.get("label") or ""
            key = str(lab).strip().lower()
            matched = False
            for k in _CLASS_KEYS:
                if key == k or key.startswith(k):
                    counts[k] += 1
                    matched = True
                    break
            if not matched:
                # try crude substring match
                for k in _CLASS_KEYS:
                    if k in key:
                        counts[k] += 1
                        break
    except Exception:
        pass

    return {
        "total": total,
        "ave_confidence": ave_conf,
        "min_confidence": min_conf,
        "max_confidence": max_conf,
        "counts": counts,
    }
