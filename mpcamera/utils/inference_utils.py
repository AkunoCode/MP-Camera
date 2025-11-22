from typing import List, Dict, Any, Optional

from mpcamera.utils.prediction_utils import extract_points_from_prediction
from mpcamera.utils.camera_utils import color_for_label


_CLASS_KEYS = ["sheet", "fragment", "fiber", "bead", "foam", "film"]


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
