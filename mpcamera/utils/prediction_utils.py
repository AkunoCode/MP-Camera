def find_predictions(obj):
    """Return a list of prediction dicts found in the inference response.

    This mirrors the heuristic used in the original controller: check for
    common wrapper keys and search nested dicts for a list of dicts.
    """
    if obj is None:
        return []
    try:
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj
        if isinstance(obj, dict):
            # common keys
            for k in ("predictions", "preds", "outputs", "results", "objects"):
                v = obj.get(k)
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
            # search deeper
            for v in obj.values():
                p = find_predictions(v)
                if p:
                    return p
    except Exception:
        pass
    return []


def extract_points_from_prediction(pred):
    """Try multiple known keys/formats to extract a list of (x,y) coords.

    Returns an empty list when none found.
    """
    try:
        # common keys that may contain point lists
        for key in ("points", "polygon", "poly", "shape"):
            if key in pred:
                pts = pred.get(key)
                # nested dict with 'data'
                if isinstance(pts, dict) and "data" in pts:
                    pts = pts.get("data")
                # flat list of numbers
                if isinstance(pts, (list, tuple)) and pts:
                    # detect a flat numeric list [x,y,x,y,...]
                    if all(isinstance(v, (int, float)) for v in pts):
                        it = iter(pts)
                        out = []
                        for x in it:
                            try:
                                y = next(it)
                            except StopIteration:
                                break
                            out.append((float(x), float(y)))
                        if out:
                            return out
                    # list of [x,y] or {'x':..,'y':..}
                    out = []
                    for item in pts:
                        try:
                            if isinstance(item, dict) and "x" in item and "y" in item:
                                out.append((float(item.get("x")), float(item.get("y"))))
                            elif (
                                isinstance(item, (list, tuple))
                                and len(item) >= 2
                                and isinstance(item[0], (int, float))
                            ):
                                out.append((float(item[0]), float(item[1])))
                        except Exception:
                            continue
                    if out:
                        return out
        # segmentation (COCO style) may be nested lists or flat
        if "segmentation" in pred:
            seg = pred.get("segmentation")
            if isinstance(seg, list) and seg:
                flat = None
                first = seg[0]
                if isinstance(first, (list, tuple)) and all(
                    isinstance(v, (int, float)) for v in first
                ):
                    flat = first
                elif all(isinstance(v, (int, float)) for v in seg):
                    flat = seg
                if flat:
                    out = []
                    it = iter(flat)
                    for x in it:
                        try:
                            y = next(it)
                        except StopIteration:
                            break
                        out.append((float(x), float(y)))
                    if out:
                        return out
        # bbox list [x,y,w,h]
        if "bbox" in pred and isinstance(pred.get("bbox"), (list, tuple)):
            bb = pred.get("bbox")
            try:
                bx = float(bb[0])
                by = float(bb[1])
                bw = float(bb[2])
                bh = float(bb[3])
                return [(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)]
            except Exception:
                pass
    except Exception:
        pass
    return []
