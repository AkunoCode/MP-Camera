"""Small helper utilities for the SoilSight UI.

This module intentionally keeps functionality small and well-tested so the
main UI file stays focused on widget wiring and view logic.

Provided helpers:
- persist_env_var(key, value): write/update `.env` at repo root
- parse_prediction_to_rows(result): convert an inference result to a list
  of (id, class_name, confidence_str) tuples ready for table insertion.
"""
from __future__ import annotations

import os
import logging
from typing import List, Tuple, Any


def persist_env_var(key: str, value: str) -> None:
    """Persist or append a KEY=VALUE entry into the repository `.env`.

    Best-effort: if `.env` doesn't exist it will be created. If the key
    exists it will be replaced; otherwise appended.
    """
    try:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        env_path = os.path.join(root, ".env")
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"{key}={value}\n")
            return

        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        found = False
        for i, ln in enumerate(lines):
            if ln.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break

        if not found:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] = lines[-1] + "\n"
            lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        logging.getLogger(__name__).debug("Failed to persist .env var %s: %s", key, e)


def _resolve_predictions_container(result: Any):
    """Return the `predictions` container or None from a result object/dict."""
    try:
        if isinstance(result, dict):
            return result.get("predictions")
        return getattr(result, "predictions", None)
    except Exception:
        return None


def parse_prediction_to_rows(result: Any) -> List[Tuple[str, str, str]]:
    """Parse an inference result into table rows.

    Returns a list of tuples: (id, class_name, confidence_str).
    The function is defensive and accepts either dict-style results or
    objects with attributes coming from the `inference` package.
    """
    rows: List[Tuple[str, str, str]] = []
    try:
        preds = _resolve_predictions_container(result)
        if preds is None:
            return rows

        # extract commonly available fields
        confidences = getattr(preds, "confidence", None)
        xyxy = getattr(preds, "xyxy", None)
        data = getattr(preds, "data", None)

        polygons = None
        try:
            if isinstance(result, dict):
                polygons = result.get("polygons")
            else:
                polygons = getattr(result, "polygons", None)
        except Exception:
            polygons = None

        # determine number of detections
        n = 0
        try:
            if hasattr(confidences, "__len__") and not isinstance(confidences, float):
                n = int(len(confidences))
            elif xyxy is not None:
                try:
                    n = int(xyxy.shape[0])
                except Exception:
                    n = 0
        except Exception:
            n = 0

        # fallback: try lengths inside data dict
        if n == 0 and isinstance(data, dict):
            for v in data.values():
                try:
                    n = int(len(v))
                    break
                except Exception:
                    continue

        for i in range(n):
            # id
            det_id = ""
            try:
                if isinstance(data, dict) and "detection_id" in data:
                    det_val = data.get("detection_id")
                    try:
                        det_id = str(det_val[i])
                    except Exception:
                        det_id = str(det_val)
                elif isinstance(data, dict) and "inference_id" in data:
                    try:
                        det_id = str(data.get("inference_id")[i])
                    except Exception:
                        det_id = str(i)
                else:
                    det_id = str(i)
            except Exception:
                det_id = str(i)

            # class name
            cls_name = ""
            try:
                if isinstance(data, dict) and "class_name" in data:
                    cls_val = data.get("class_name")
                    try:
                        cls_name = str(cls_val[i])
                    except Exception:
                        cls_name = str(cls_val)
                else:
                    val = getattr(preds, "class_name", None)
                    if val is not None:
                        try:
                            cls_name = str(val[i])
                        except Exception:
                            cls_name = str(val)
            except Exception:
                cls_name = ""

            # confidence
            conf_val = ""
            try:
                if confidences is not None:
                    try:
                        c = float(confidences[i])
                        conf_val = f"{c:.3f}"
                    except Exception:
                        conf_val = str(confidences[i])
            except Exception:
                conf_val = ""

            rows.append((det_id, cls_name, conf_val))

    except Exception:
        # be conservative: return whatever parsed so far
        return rows

    return rows
