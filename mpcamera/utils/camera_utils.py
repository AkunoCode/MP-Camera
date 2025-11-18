from PyQt6 import QtGui
import pathlib

# debug log file (repo root)
_log_path = pathlib.Path(__file__).resolve().parents[2] / "prediction_debug.txt"


def append_log(msg: str):
    try:
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def color_for_label(label: str):
    try:
        if not label:
            return QtGui.QColor(255, 0, 0, 140)
        h = abs(hash(label)) % 360
        c = QtGui.QColor.fromHsv(h, 200, 200, 180)
        return c
    except Exception:
        return QtGui.QColor(255, 0, 0, 140)


def extract_directus_items(obj):
    if obj is None:
        return []
    try:
        if isinstance(obj, dict) and "data" in obj:
            return obj.get("data") or []
        if isinstance(obj, list):
            return obj
    except Exception:
        pass
    return []


def get_site_id_from_sample(sample_item):
    if sample_item is None:
        return None
    try:
        site = sample_item.get("site")
        if isinstance(site, dict):
            return site.get("id")
        return site
    except Exception:
        return None
