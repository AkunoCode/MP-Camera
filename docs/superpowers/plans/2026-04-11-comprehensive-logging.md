# Comprehensive Logging Sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every failure in SoilSight visible in `~/.mpcamera/debug.log` by fixing ~90 silent exception blocks and replacing all `print()` calls with proper logger calls across 8 files.

**Architecture:** Pure sweep — no new classes or infrastructure. Every module already uses `logging.getLogger(__name__)` which flows through the root logger configured by `setup_logging()` in `main.py`. Work is strictly: (1) replace bare `except Exception:` with `logger.error/warning/debug`, (2) replace `print()` calls with `logger.*`, (3) add structured boundary log lines at inference/upload/model-load entry and exit points.

**Tech Stack:** Python `logging` stdlib only. PyQt6, OpenCV, PyTorch for context. No new dependencies.

---

## Verification Approach

This plan adds observability — it does not change behavior. There is no meaningful TDD cycle for "logger was called." Instead, each task ends with a manual smoke check:

```bash
# After each task, launch the app and exercise the relevant code path, then:
tail -50 ~/.mpcamera/debug.log
```

Look for the specific log lines specified in each task. If failures occur, they must now appear with a full traceback (`exc_info=True`).

---

## Severity Guide (reference for all tasks)

| Situation | Level |
|---|---|
| Optional import fallback at module top | `logger.debug(...)` |
| Fallback path taken, feature still works | `logger.warning("...", exc_info=True)` |
| Failure that breaks a feature | `logger.error("...", exc_info=True)` |
| Key pipeline event (inference, upload, model load) | `logger.info(...)` |
| Low-level detail (per-particle, per-frame) | `logger.debug(...)` |

---

## Task 1: `mpcamera/config.py` — Replace prints, fix silent except

**Files:**
- Modify: `mpcamera/config.py:104-108`, `mpcamera/config.py:117-118`, `mpcamera/config.py:196`

- [ ] **Step 1: Fix `Settings.load` — invalid JSON print (line 104-108)**

Replace:
```python
            except json.JSONDecodeError:
                print(
                    f"Warning: Invalid JSON in {u_path}, using defaults.",
                    file=sys.stderr,
                )
```
With:
```python
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in {u_path}, using schema defaults")
```

- [ ] **Step 2: Fix `Settings.load` — validation warning print (line 117-118)**

Replace:
```python
            except jsonschema.ValidationError as e:
                print(f"Config validation warning: {e.message}", file=sys.stderr)
```
With:
```python
            except jsonschema.ValidationError as e:
                logger.warning(f"Config validation warning: {e.message}")
```

- [ ] **Step 3: Fix `sync_env_to_config` — silent except (line 195-197)**

Replace:
```python
    try:
        cfg.save()
    except Exception:
        pass
```
With:
```python
    try:
        cfg.save()
    except Exception:
        logger.error("Failed to save config after env sync", exc_info=True)
```

- [ ] **Step 4: Remove unused `sys` import if it's now only used for `file=sys.stderr`**

Check line 7: `import sys` — after step 1 and 2 above, `sys` is no longer used in `config.py`. Remove it:
```python
# Remove: import sys
```
(Only remove if `sys` is not referenced elsewhere in the file — do a quick scan first.)

- [ ] **Step 5: Verify**

```bash
python -c "from mpcamera.config import Settings; Settings.load()" 2>&1
tail -5 ~/.mpcamera/debug.log
```
Expected: no `print` output to stderr. Any config issue appears in log.

- [ ] **Step 6: Commit**

```bash
git add mpcamera/config.py
git commit -m "fix(logging): replace print() with logger in config.py"
```

---

## Task 2: `mpcamera/services/roboflow.py` — Replace print, fix silent excepts

**Files:**
- Modify: `mpcamera/services/roboflow.py:8`, `mpcamera/services/roboflow.py:68-71`, `mpcamera/services/roboflow.py:176`

- [ ] **Step 1: Fix module-level import fallback (line 6-9)**

Replace:
```python
try:
    from mpcamera.config import get_settings
except Exception:
    get_settings = None
```
With:
```python
try:
    from mpcamera.config import get_settings
except Exception as _e:
    logger.debug(f"mpcamera.config unavailable in roboflow: {_e}")
    get_settings = None
```

- [ ] **Step 2: Fix `_create_client` print (line 68-71)**

Replace:
```python
        except Exception as e:
            # Do not raise — caller should handle absence of dependency gracefully.
            self._client = None
            print("RoboflowClient: failed to import inference_sdk or create client:", e)
```
With:
```python
        except Exception as e:
            # Do not raise — caller should handle absence of dependency gracefully.
            self._client = None
            logger.error("Failed to create RoboflowClient (inference_sdk missing or misconfigured)", exc_info=True)
```

- [ ] **Step 3: Fix `_get_roboflow_settings` silent except (line 175-177)**

Replace:
```python
    except Exception:
        return {}
```
With:
```python
    except Exception:
        logger.debug("Could not read Roboflow settings from config", exc_info=True)
        return {}
```

- [ ] **Step 4: Verify**

```bash
python -c "from mpcamera.services.roboflow import RoboflowClient; c = RoboflowClient()"
tail -10 ~/.mpcamera/debug.log
```
Expected: no print output. If `inference_sdk` is missing, log shows `ERROR ... Failed to create RoboflowClient`.

- [ ] **Step 5: Commit**

```bash
git add mpcamera/services/roboflow.py
git commit -m "fix(logging): replace print() with logger in roboflow.py"
```

---

## Task 3: `mpcamera/services/directus.py` — Fix silent excepts

**Files:**
- Modify: `mpcamera/services/directus.py:27-29`, `mpcamera/services/directus.py:147-149`

- [ ] **Step 1: Fix dotenv import fallback (line 23-29)**

Replace:
```python
try:
    # load .env in development if present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    load_dotenv = None
```
With:
```python
try:
    # load .env in development if present
    from dotenv import load_dotenv

    load_dotenv()
except Exception as _e:
    logger.debug(f"dotenv not available in directus: {_e}")
    load_dotenv = None
```

- [ ] **Step 2: Fix `upload_file` mime-type detection silent except (line 147-149)**

Replace:
```python
        except Exception:
            pass
```
With:
```python
        except Exception:
            logger.debug("Could not detect MIME type from extension; using image/png")
```

- [ ] **Step 3: Verify**

```bash
python -c "from mpcamera.services.directus import DirectusClient; DirectusClient()"
tail -5 ~/.mpcamera/debug.log
```
Expected: no exceptions swallowed silently.

- [ ] **Step 4: Commit**

```bash
git add mpcamera/services/directus.py
git commit -m "fix(logging): fix silent except blocks in directus.py"
```

---

## Task 4: `mpcamera/utils/inference_utils.py` — Add logger, fix silents, add boundary logs

**Files:**
- Modify: `mpcamera/utils/inference_utils.py:1-6` (add logger), multiple silent blocks, `parse_result_to_preds`, `apply_confidence_iou_filters`, `compute_aggregates`

- [ ] **Step 1: Add logger import at top of file (after existing imports)**

After line 6 (`from mpcamera.utils.camera_utils import color_for_label`), add:
```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Fix `_pred_to_xyxy` polygon fallback silent except (~line 77)**

Replace:
```python
    except Exception:
        pass
```
(the one inside the `try: pts = extract_points_from_prediction(pred)` block)
With:
```python
    except Exception:
        logger.debug("Failed to extract bbox from polygon points", exc_info=True)
```

- [ ] **Step 3: Fix `apply_confidence_iou_filters._walk` silent except (~line 246)**

Replace:
```python
        except Exception:
            return
```
With:
```python
        except Exception:
            logger.warning("apply_confidence_iou_filters: error walking prediction tree", exc_info=True)
            return
```

- [ ] **Step 4: Fix `_collect_pred_dicts` silent except (~line 308)**

Replace:
```python
    except Exception:
        return out
```
With:
```python
    except Exception:
        logger.warning("_collect_pred_dicts: error collecting predictions from result", exc_info=True)
        return out
```

- [ ] **Step 5: Fix `parse_result_to_preds` inner silent excepts (~lines 340, 346, 365)**

For the `except Exception: score = None` block (score parsing):
```python
                    except Exception:
                        score = None
```
Leave as-is — this is an expected numeric conversion, not a failure.

For the `except Exception: pts = []` block (points extraction):
```python
            except Exception:
                pts = []
```
Replace with:
```python
            except Exception:
                logger.debug("Failed to extract points from prediction", exc_info=True)
                pts = []
```

For the outer `except Exception: continue` (skipping malformed prediction):
```python
        except Exception:
            continue
```
Replace with:
```python
        except Exception:
            logger.warning("Skipping malformed prediction dict", exc_info=True)
            continue
```

- [ ] **Step 6: Fix `compute_aggregates` silent excepts (~lines 386, 390, 392, 414)**

For `min_conf` and `max_conf` inner blocks (lines ~385-395):
```python
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
```
Replace with:
```python
            try:
                min_conf = min(confidences)
            except Exception:
                logger.debug("Could not compute min confidence")
                min_conf = None
            try:
                max_conf = max(confidences)
            except Exception:
                logger.debug("Could not compute max confidence")
                max_conf = None
    except Exception:
        logger.warning("compute_aggregates: failed to compute confidence stats", exc_info=True)
        ave_conf = None
        min_conf = None
        max_conf = None
```

For the class-count `except Exception: pass` (~line 414):
```python
    except Exception:
        pass
```
Replace with:
```python
    except Exception:
        logger.warning("compute_aggregates: failed to count classes", exc_info=True)
```

- [ ] **Step 7: Add boundary log lines to `parse_result_to_preds`**

At the start of `parse_result_to_preds` (after `flat = _collect_pred_dicts(result)`):
```python
    logger.debug(f"parse_result_to_preds: collected {len(flat)} raw prediction dicts")
```

At the end, before `return out`:
```python
    logger.debug(f"parse_result_to_preds: parsed {len(out)} valid predictions")
```

- [ ] **Step 8: Add boundary log lines to `apply_confidence_iou_filters`**

Before `_walk(result)`:
```python
    logger.debug(f"apply_confidence_iou_filters: conf={confidence_threshold}, iou={iou_threshold}")
```

- [ ] **Step 9: Verify**

```bash
python -c "
from mpcamera.utils.inference_utils import parse_result_to_preds, apply_confidence_iou_filters
result = [{'class': 'fragment', 'confidence': 0.9, 'points': []}]
preds = parse_result_to_preds(result)
apply_confidence_iou_filters(result, 0.5, 0.5)
print('OK', len(preds))
"
tail -10 ~/.mpcamera/debug.log
```
Expected: log shows `parse_result_to_preds: collected 1 raw prediction dicts` and `parsed 1 valid predictions`.

- [ ] **Step 10: Commit**

```bash
git add mpcamera/utils/inference_utils.py
git commit -m "fix(logging): add logger and fix silent excepts in inference_utils.py"
```

---

## Task 5: `mpcamera/ui/zoomable_view.py` — Add logger, fix silent excepts

**Files:**
- Modify: `mpcamera/ui/zoomable_view.py` (all ~22 silent blocks)

Note: All exceptions in this file are Qt UI operations (zoom, pan, key handling). They cannot meaningfully break core functionality. Use `logger.debug` throughout — `logger.warning` only if the fallback path itself also fails.

- [ ] **Step 1: Add logger import**

After `from PyQt6 import QtWidgets, QtCore, QtGui` (line 1), add:
```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Fix `__init__` silent excepts (lines ~34, 39, 44)**

Replace each bare `except Exception: pass` in `__init__` with `logger.debug`:

```python
        try:
            self.setTransformationAnchor(
                QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
            )
            self.setResizeAnchor(
                QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter
            )
        except Exception:
            logger.debug("Could not set transformation anchor", exc_info=True)
        try:
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        except Exception:
            logger.debug("Could not set drag mode", exc_info=True)
        try:
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        except Exception:
            logger.debug("Could not set focus policy", exc_info=True)
```

- [ ] **Step 3: Fix `wheelEvent` silent excepts (lines ~64-69)**

Replace:
```python
        except Exception:
            # fallback to base implementation
            try:
                super().wheelEvent(event)
            except Exception:
                pass
```
With:
```python
        except Exception:
            logger.debug("wheelEvent error; falling back to base implementation", exc_info=True)
            try:
                super().wheelEvent(event)
            except Exception:
                logger.debug("wheelEvent base fallback also failed")
```

- [ ] **Step 4: Fix `zoom_in`, `zoom_out`, `reset_zoom`, `set_pan_enabled` silent excepts**

Replace each `except Exception: pass` in these methods with `logger.debug`:

```python
    def zoom_in(self):
        try:
            if self._zoom_level < self._zoom_max:
                self._zoom_level += 1
                self.scale(self._zoom_step, self._zoom_step)
        except Exception:
            logger.debug("zoom_in failed", exc_info=True)

    def zoom_out(self):
        try:
            if self._zoom_level > self._zoom_min:
                self._zoom_level -= 1
                self.scale(1.0 / self._zoom_step, 1.0 / self._zoom_step)
        except Exception:
            logger.debug("zoom_out failed", exc_info=True)

    def reset_zoom(self):
        try:
            self.resetTransform()
            self._zoom_level = 0
            if self.scene() is not None:
                rect = self.scene().itemsBoundingRect()
                if rect.isValid():
                    self.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        except Exception:
            logger.debug("reset_zoom failed", exc_info=True)

    def set_pan_enabled(self, enabled: bool):
        try:
            if enabled:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            else:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        except Exception:
            logger.debug("set_pan_enabled failed", exc_info=True)
```

- [ ] **Step 5: Fix `mouseDoubleClickEvent` silent excepts (lines ~111-115)**

Replace:
```python
        except Exception:
            try:
                super().mouseDoubleClickEvent(event)
            except Exception:
                pass
```
With:
```python
        except Exception:
            logger.debug("mouseDoubleClickEvent reset_zoom failed; falling back to base", exc_info=True)
            try:
                super().mouseDoubleClickEvent(event)
            except Exception:
                logger.debug("mouseDoubleClickEvent base fallback also failed")
```

- [ ] **Step 6: Fix `mousePressEvent` silent excepts (lines ~121-129)**

Replace:
```python
        try:
            # ensure the view receives focus when clicked so key events are delivered
            try:
                self.setFocus()
            except Exception:
                pass
        except Exception:
            pass
        try:
            super().mousePressEvent(event)
        except Exception:
            pass
```
With:
```python
        try:
            self.setFocus()
        except Exception:
            logger.debug("mousePressEvent setFocus failed")
        try:
            super().mousePressEvent(event)
        except Exception:
            logger.debug("mousePressEvent base call failed", exc_info=True)
```

- [ ] **Step 7: Fix `keyPressEvent` and `keyReleaseEvent` silent excepts**

Replace the bare `except Exception: pass` blocks in both methods with `logger.debug`:

```python
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        try:
            if event.key() == QtCore.Qt.Key.Key_Space:
                try:
                    self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
                    vp = self.viewport()
                    try:
                        vp.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    except Exception:
                        logger.debug("keyPressEvent: could not set closed hand cursor")
                except Exception:
                    logger.debug("keyPressEvent: could not set scroll hand drag mode", exc_info=True)
                return
        except Exception:
            logger.debug("keyPressEvent: Space key handler failed", exc_info=True)
        try:
            super().keyPressEvent(event)
        except Exception:
            logger.debug("keyPressEvent base call failed", exc_info=True)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        try:
            if event.key() == QtCore.Qt.Key.Key_Space:
                try:
                    self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
                    vp = self.viewport()
                    try:
                        vp.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                    except Exception:
                        logger.debug("keyReleaseEvent: could not restore arrow cursor")
                except Exception:
                    logger.debug("keyReleaseEvent: could not restore NoDrag mode", exc_info=True)
                return
        except Exception:
            logger.debug("keyReleaseEvent: Space key handler failed", exc_info=True)
        try:
            super().keyReleaseEvent(event)
        except Exception:
            logger.debug("keyReleaseEvent base call failed", exc_info=True)
```

- [ ] **Step 8: Verify**

```bash
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mpcamera.ui.zoomable_view import ZoomableGraphicsView
v = ZoomableGraphicsView()
v.zoom_in()
v.zoom_out()
v.reset_zoom()
print('OK')
"
tail -5 ~/.mpcamera/debug.log
```
Expected: no errors. Any unexpected Qt issue now appears as DEBUG in log.

- [ ] **Step 9: Commit**

```bash
git add mpcamera/ui/zoomable_view.py
git commit -m "fix(logging): add logger and replace silent excepts in zoomable_view.py"
```

---

## Task 6: `mpcamera/ui/results_window.py` — Replace prints, fix silent excepts

**Files:**
- Modify: `mpcamera/ui/results_window.py`

- [ ] **Step 1: Verify logger is set up**

Check that line ~8 contains `logger = logging.getLogger(__name__)`. If not, add after imports:
```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Fix initialization silent excepts (lines ~34, 44, 56, 77)**

These are in widget initialization methods. Replace each `except Exception: pass` with the appropriate logger call. For example (adapt message to match the surrounding context):

Line ~34 (inside `_setup_table` or similar init):
```python
        except Exception:
            logger.warning("results_window: error during table setup", exc_info=True)
```

Line ~44:
```python
        except Exception:
            logger.warning("results_window: error during column setup", exc_info=True)
```

Line ~56:
```python
        except Exception:
            logger.warning("results_window: error populating initial data", exc_info=True)
```

Line ~77:
```python
        except Exception:
            logger.warning("results_window: error during UI initialization", exc_info=True)
```

Read the surrounding code for each block to write a descriptive message that reflects what actually failed.

- [ ] **Step 3: Replace print at line ~185**

Replace:
```python
                print(f"[RESULTS] Table capped at {MAX_ROWS} rows — truncating display")
```
With:
```python
                logger.warning(f"Results table capped at {MAX_ROWS} rows — truncating display")
```

- [ ] **Step 4: Fix silent excepts in table population loop (~line 203, 280, 312, 337, 345, 353, 363, 416)**

For each bare `except Exception: pass` in table row population, replace with:
```python
        except Exception:
            logger.warning("results_window: error populating table row", exc_info=True)
```

Read the surrounding code for each block to add a descriptive message.

- [ ] **Step 5: Replace print at line ~303 (delete row error)**

Replace:
```python
            print(f"Error deleting row: {e}")
```
With:
```python
            logger.error(f"Error deleting row", exc_info=True)
```

- [ ] **Step 6: Replace print at line ~315 (Directus upload start)**

Replace:
```python
        print(f"Updating {len(self._cached_morphometrics)} records...")
```
With:
```python
        logger.info(f"Uploading {len(self._cached_morphometrics)} morphometric records to Directus")
```

- [ ] **Step 7: Add Directus upload boundary log (after the upload loop completes)**

In the method that uploads to Directus, after the loop that uploads records, add:
```python
        logger.info(f"Directus upload complete: {success_count} records uploaded")
```
(Add a `success_count` counter if one doesn't exist in that method.)

- [ ] **Step 8: Verify**

Launch the app, run inference, open the results window. Then:
```bash
tail -20 ~/.mpcamera/debug.log
```
Expected: `Uploading N morphometric records to Directus` appears, and if upload fails, a full traceback appears.

- [ ] **Step 9: Commit**

```bash
git add mpcamera/ui/results_window.py
git commit -m "fix(logging): replace print() and silent excepts in results_window.py"
```

---

## Task 7: `mpcamera/utils/local_models_utils.py` — Replace prints, add boundary logs

**Files:**
- Modify: `mpcamera/utils/local_models_utils.py`

Note: This file has no logger. First add it.

- [ ] **Step 1: Add logger**

After the existing imports (after line ~15 `warnings.filterwarnings(...)`), add:
```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Replace `__init__` prints**

Replace line ~88:
```python
        print(f"[INFO] Loading {os.path.basename(self.model_path)} on {self.device}...")
```
With:
```python
        logger.info(f"Loading model '{os.path.basename(self.model_path)}' on device '{self.device}'")
```

Replace lines ~94-97 (checkpoint load failure):
```python
        except Exception as e:
            print(
                f"[WARNING] Failed to load checkpoint dictionary directly: {e}. Relying on model path for architecture detection."
            )
            self.checkpoint = {}
```
With:
```python
        except Exception as e:
            logger.warning(f"Failed to load checkpoint dict from '{self.model_path}'; will infer architecture from filename. Error: {e}")
            self.checkpoint = {}
```

- [ ] **Step 3: Replace `_resolve_model_path` print (line ~132)**

Replace:
```python
                print(f"[MODEL] Resolved model path: {resolved}")
```
With:
```python
                logger.debug(f"Resolved model path: {resolved}")
```

- [ ] **Step 4: Replace `_determine_model_type` prints (lines ~154, 173, 181, 185)**

Replace each `print(" -> Detected Model Type: X")` with:
```python
        logger.info(f"Detected model architecture: RF-DETR-SEG")
        # (adapt the architecture name per branch)
```

Specifically:
- Line ~154: `logger.info("Detected model architecture: RF-DETR-SEG")`
- Line ~173: `logger.info("Detected model architecture: YOLOv11 (Ultralytics)")`
- Line ~181: `logger.info("Detected model architecture: YOLOv11 (Ultralytics) — .pt extension")`
- Line ~185: `logger.info("Detected model architecture: MaskRCNN (default fallback)")`

- [ ] **Step 5: Replace `_smart_load_model` prints (lines ~212, 234, 239, 248)**

Replace each `print(" -> Successfully loaded as X")`:
- Line ~212: `logger.info(f"RF-DETR-SEG loaded successfully on device '{self.device}'")`
- Line ~234: `logger.info("MaskRCNN-ResNet50 loaded successfully")`
- Line ~239: (the one inside a nested try): `logger.info("MaskRCNN-ResNet101 loaded successfully")`
- Line ~248: `logger.info("MaskRCNN-ResNet101 (alternate) loaded successfully")`

Also add an error log for load failures:
```python
        except Exception as e:
            logger.error(f"Failed to load model from '{self.model_path}'", exc_info=True)
            raise
```

- [ ] **Step 6: Replace inference warning prints (lines ~417, 490)**

Replace line ~417:
```python
            print("[WARNING] YOLO model did not return segmentation masks.")
```
With:
```python
            logger.warning("YOLO model did not return segmentation masks; proceeding without mask data")
```

Replace line ~490:
```python
            print("[WARNING] RF-DETR-SEG model did not return segmentation masks.")
```
With:
```python
            logger.warning("RF-DETR-SEG model did not return segmentation masks; proceeding without mask data")
```

- [ ] **Step 7: Fix `__init__` config-loading silent except (~line 79-82)**

Replace:
```python
        except Exception:
            confidence_threshold = confidence_threshold or 0.5
            iou_threshold = iou_threshold or 0.4
            device = device or ("cuda" if torch.cuda.is_available() else "cpu")
```
With:
```python
        except Exception:
            logger.warning("Could not read inference config; using defaults (conf=0.5, iou=0.4)", exc_info=True)
            confidence_threshold = confidence_threshold or 0.5
            iou_threshold = iou_threshold or 0.4
            device = device or ("cuda" if torch.cuda.is_available() else "cpu")
```

- [ ] **Step 8: Verify**

If a local model exists in `models/`, run:
```bash
python -c "
from mpcamera.utils.local_models_utils import LocalModelInference
# (if models/ is empty this will raise FileNotFoundError which is expected)
" 2>&1
tail -10 ~/.mpcamera/debug.log
```
Expected: `Loading model '...' on device 'cpu'` and `Detected model architecture: ...` appear in log.

- [ ] **Step 9: Commit**

```bash
git add mpcamera/utils/local_models_utils.py
git commit -m "fix(logging): replace print() with logger in local_models_utils.py"
```

---

## Task 8: `mpcamera/controllers/camera_page.py` — Replace prints, fix silent excepts, add boundary logs

**Files:**
- Modify: `mpcamera/controllers/camera_page.py`

This is the largest task (~40 silent blocks + ~10 print calls). Work through the file top-to-bottom.

- [ ] **Step 1: Fix top-level import fallback silents (lines ~39, 43, 47, 71)**

Replace each:
```python
    except ImportError:
        X = None
    # or
    except Exception:
        X = None
```
With (adapt the name per import):
```python
    except Exception as _e:
        logger.debug(f"Optional import 'InferenceWorker' unavailable: {_e}")
        InferenceWorker = None
```

Do this for: `InferenceWorker`, `FormHandler`, `ResultsWindow`, `adjust_brightness_contrast`, `LocalModelInference`.

- [ ] **Step 2: Fix `__init__` config-loading silent excepts (lines ~173-230)**

Replace all the nested `except Exception: pass` in the config-loading block with descriptive debug messages. For example:

```python
            try:
                self._frame_timer.setInterval(int(cfg.streaming.frame_interval_ms))
            except Exception:
                logger.debug("Could not read streaming.frame_interval_ms from config")
            try:
                self._stream_inference_timer.setInterval(
                    int(cfg.streaming.inference_interval_ms)
                )
            except Exception:
                logger.debug("Could not read streaming.inference_interval_ms from config")
            try:
                self.DEFAULT_CONFIDENCE = float(cfg.inference.default_confidence)
            except Exception:
                logger.debug("Could not read inference.default_confidence from config")
            try:
                self.DEFAULT_IOU = float(cfg.inference.default_iou)
            except Exception:
                logger.debug("Could not read inference.default_iou from config")
```

Continue this pattern for all remaining nested config blocks (default model, local models dir, prefer_local, brightness, contrast).

For the outer `except Exception:` at line ~226:
```python
        except Exception:
            logger.warning("Could not load any settings; using class defaults", exc_info=True)
            self._brightness_default = 50
            self._contrast_default = 50
            self.LOCAL_MODELS_DIR = self._resolve_local_models_dir(self.LOCAL_MODELS_DIR)
```

- [ ] **Step 3: Fix InferenceWorker and FormHandler init silents (~lines 255-264)**

Replace:
```python
        try:
            self._inference_worker = InferenceWorker()
            self._inference_worker.finished.connect(self._on_inference_worker_finished)
            self._inference_worker.error.connect(self._on_inference_worker_error)
        except Exception:
            self._inference_worker = None
```
With:
```python
        try:
            self._inference_worker = InferenceWorker()
            self._inference_worker.finished.connect(self._on_inference_worker_finished)
            self._inference_worker.error.connect(self._on_inference_worker_error)
        except Exception:
            logger.error("Failed to initialize InferenceWorker", exc_info=True)
            self._inference_worker = None
```

Replace:
```python
        try:
            self._form_handler = FormHandler(
                self.ui.get("farm_combo"), self.ui.get("soil_combo")
            )
        except Exception:
            self._form_handler = None
```
With:
```python
        try:
            self._form_handler = FormHandler(
                self.ui.get("farm_combo"), self.ui.get("soil_combo")
            )
        except Exception:
            logger.warning("Failed to initialize FormHandler", exc_info=True)
            self._form_handler = None
```

- [ ] **Step 4: Replace `_find_ui_elements` print (~line 423)**

Replace:
```python
        if missing:
            print(f"[CAMERA PAGE] Warning: UI elements not found: {missing}")
```
With:
```python
        if missing:
            logger.warning(f"UI elements not found: {missing}")
```

- [ ] **Step 5: Fix `_init_ui_defaults` silent excepts (~lines 506-548)**

Replace the `except Exception: pass` in slider and UI initialization with `logger.debug`:

```python
        try:
            self._update_param_labels()
        except Exception:
            logger.debug("_update_param_labels failed during init", exc_info=True)

        try:
            self._apply_adjustments_and_refresh()
        except Exception:
            logger.debug("_apply_adjustments_and_refresh failed during init", exc_info=True)
```

For brightness/contrast slider setup:
```python
        try:
            # ... slider setup ...
        except Exception:
            logger.warning("Failed to set up brightness/contrast sliders", exc_info=True)
```

- [ ] **Step 6: Fix prefer_local_model selection silent except (~line 575-576)**

Replace:
```python
                except Exception:
                    selected_local = False
```
With:
```python
                except Exception:
                    logger.debug("Could not select local model from combo", exc_info=True)
                    selected_local = False
```

- [ ] **Step 7: Replace `_populate_local_models` prints (~lines 626, 644, 658)**

Replace line ~626:
```python
            print(f"[CAMERA PAGE] Models directory not found: {self.LOCAL_MODELS_DIR}")
```
With:
```python
            logger.warning(f"Local models directory not found: {self.LOCAL_MODELS_DIR}")
```

Replace line ~644:
```python
            print(f"[CAMERA PAGE] No .pt/.pth files found in {self.LOCAL_MODELS_DIR}")
```
With:
```python
            logger.info(f"No .pt/.pth model files found in {self.LOCAL_MODELS_DIR}")
```

Replace line ~658:
```python
        print(f"[CAMERA PAGE] Found {len(model_files)} local models.")
```
With:
```python
        logger.info(f"Found {len(model_files)} local model files in {self.LOCAL_MODELS_DIR}")
```

- [ ] **Step 8: Replace `_replace_graphics_view` prints (~lines 706-709)**

Replace:
```python
        except ImportError:
            print("ZoomableGraphicsView not found, using default.")
        except Exception as e:
            print(f"View replacement failed: {e}")
```
With:
```python
        except ImportError:
            logger.warning("ZoomableGraphicsView not available; using default QGraphicsView")
        except Exception as e:
            logger.error("Failed to replace graphics view with ZoomableGraphicsView", exc_info=True)
```

- [ ] **Step 9: Replace `_populate_data` prints (~lines 719-758)**

Replace all `print(...)` in `_populate_data` with logger calls:

```python
    def _populate_data(self):
        try:
            logger.debug(f"_populate_data: thread={threading.current_thread().name}")

            self.ui = self._find_ui_elements()

            get_sites = getattr(self.main_window, "get_sites", lambda: [])
            get_soils = getattr(self.main_window, "get_soilsamples", lambda: [])

            sites = extract_directus_items(get_sites())
            soils = extract_directus_items(get_soils())

            logger.debug(f"_populate_data: sites={len(sites) if sites else 0}, soils={len(soils) if soils else 0}")

            self._cached_soils = soils or []
            setattr(self.main_window, "_camera_sites_list", sites)
            setattr(self.main_window, "_camera_soils_list", self._cached_soils)

            self._update_farm_combo(sites)

            current_farm_id = None
            if self.ui["farm_combo"] is not None:
                current_farm_id = self.ui["farm_combo"].currentData()

            logger.debug(f"_populate_data: filtering soils by farm_id={current_farm_id}")
            self._filter_soil_combo(current_farm_id)

        except Exception as e:
            logger.error("Camera page data population failed", exc_info=True)
```

- [ ] **Step 10: Replace `_update_farm_combo` print (~line 768)**

Replace:
```python
            print("[CAMERA PAGE] update_farm_combo: No sites to add.")
```
With:
```python
            logger.debug("update_farm_combo: no sites available")
```

- [ ] **Step 11: Fix remaining silent excepts in camera_page.py**

Scan from line 800 to end of file for any remaining bare `except Exception: pass` or `except Exception: continue`. For each one, read the surrounding context and add the appropriate log call. Pattern:

- If inside a UI rendering or display method: `logger.warning("...", exc_info=True)`
- If inside an inference or data-processing method: `logger.error("...", exc_info=True)`
- If inside an optional/cleanup path: `logger.debug("...")`

- [ ] **Step 12: Add inference trigger boundary log**

Find the method that triggers inference (search for `InferenceWorker` usage or `_run_inference`). At the entry point where inference is actually started, add:

```python
        logger.info(f"Inference triggered: model='{selected_model}', sample_id={sample_id}, frame_shape={frame.shape if frame is not None else None}")
```

At the inference completion handler (`_on_inference_worker_finished` or similar), add:

```python
        logger.info(f"Inference complete: {len(preds)} particles detected")
```

- [ ] **Step 13: Verify**

Launch the app, select a model, select a farm/soil sample, open a camera (or load an image), and trigger inference. Then:

```bash
tail -30 ~/.mpcamera/debug.log
```

Expected lines in log:
- `INFO ... Inference triggered: model='...', sample_id=...`
- `INFO ... Inference complete: N particles detected`
- `INFO ... Found N local model files in ...` (or warning if no models dir)
- No bare `print()` output to console

- [ ] **Step 14: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix(logging): replace print() and silent excepts in camera_page.py, add inference boundary logs"
```

---

## Final Verification

- [ ] **Run the full app and exercise all paths**

```bash
python main.py &
# In the app: open camera, run inference, save results to Directus
# Then:
tail -100 ~/.mpcamera/debug.log | grep -E "ERROR|WARNING"
```

Expected: any failures that previously disappeared silently now appear as `ERROR` with full tracebacks.

- [ ] **Confirm no print() calls remain in modified files**

```bash
grep -rn "print(" mpcamera/controllers/camera_page.py mpcamera/ui/results_window.py mpcamera/utils/local_models_utils.py mpcamera/services/roboflow.py mpcamera/config.py
```

Expected: no output (or only comments containing "print").

- [ ] **Confirm no silent except blocks remain**

```bash
grep -A1 "except Exception:" mpcamera/controllers/camera_page.py mpcamera/ui/results_window.py mpcamera/utils/inference_utils.py mpcamera/ui/zoomable_view.py | grep -v "logger\." | grep -v "^\-\-$" | grep -v "except Exception"
```

Expected: no lines that are just `pass` or `continue` without a logger call before them.
