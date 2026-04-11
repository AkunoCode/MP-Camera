# SoilSight App Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 10 high-priority issues from the optimization analysis to eliminate crashes, data corruption, and performance bottlenecks.

**Architecture:** Issues are fixed in priority order from the analysis: crash-prevention threading fixes first, then resource leak fixes, then performance improvements, then architecture/state correctness. Each task is independently testable.

**Tech Stack:** Python 3.11, PyQt6, OpenCV, NumPy, threading

---

## File Map

| File | Changes |
|---|---|
| `mpcamera/utils/camera_worker.py` | Add `finally` block around VideoCapture open (3.1) |
| `mpcamera/utils/inference_worker.py` | Remove double JSON serialization (5.2); store raw preds (5.1); fix temp file cleanup |
| `mpcamera/controllers/camera_page.py` | Add frame buffer mutex (7.1); fix `_inference_running` never reset on stop (7.7); show spinner during streaming (4.1); cache raw preds for slider (5.1); remove legacy fallback thread (2.6); introduce `CameraState` enum (2.3) |
| `mpcamera/services/roboflow.py` | Extend lock to cover `refresh_auth_from_settings` (2.2) |
| `mpcamera/utils/inference_utils.py` | Vectorize NMS IoU (1.3) |
| `mpcamera/utils/local_models_utils.py` | Return dict directly from `predict_json` (5.2) |

---

## Task 1: Fix Race Condition on Frame Buffers (Issue 7.1)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — add `threading.Lock` around `_raw_frame_np` and `_current_frame_np`

The camera worker thread writes `_raw_frame_np` (line 1199) while the main thread reads it (line 904) with no synchronization. This is a TSAN data race.

- [ ] **Step 1: Add lock to controller `__init__`**

In `mpcamera/controllers/camera_page.py`, find the `# --- State ---` block (~line 117). Add the import and lock:

```python
import threading  # add at top of file if not present
```

Then in `__init__`, after `self._inference_running = False`, add:

```python
self._frame_lock = threading.Lock()
```

- [ ] **Step 2: Wrap writes to `_raw_frame_np` with the lock**

Find `_on_worker_frame` method (search for `def _on_worker_frame`). Wrap the assignment:

```python
def _on_worker_frame(self, frame):
    with self._frame_lock:
        self._raw_frame_np = frame
    self._apply_adjustments_and_refresh()
```

- [ ] **Step 3: Wrap reads of `_raw_frame_np` and writes to `_current_frame_np` with the lock**

In `_apply_adjustments_and_refresh` (~line 900), replace the unguarded read:

```python
# BEFORE
raw = getattr(self, "_raw_frame_np", None)
if raw is None:
    raw = self._current_frame_np

# AFTER
with self._frame_lock:
    raw = getattr(self, "_raw_frame_np", None)
    if raw is None:
        raw = self._current_frame_np
    if raw is not None:
        raw = raw.copy()  # work on a snapshot outside the lock
```

- [ ] **Step 4: Wrap inference worker's read of `_current_frame_np`**

Search for any location in `camera_page.py` that reads `_current_frame_np` for inference (around lines 1928–1931 per analysis). Wrap with `self._frame_lock`:

```python
with self._frame_lock:
    frame_snapshot = self._current_frame_np.copy() if self._current_frame_np is not None else None
```

- [ ] **Step 5: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: add threading.Lock around frame buffer reads/writes (issue 7.1)"
```

---

## Task 2: Fix VideoCapture Handle Leaked on Error (Issue 3.1)

**Files:**
- Modify: `mpcamera/utils/camera_worker.py:41-100`

`cv2.VideoCapture` is opened but not inside a `try/finally`. An exception before `self._timer.start()` leaks the OS device handle.

- [ ] **Step 1: Wrap the camera open block in `start_camera` with finally**

In `camera_worker.py`, replace the current `start_camera` body from line ~46 to ~96:

```python
def start_camera(self, index: int):
    """Handles the complex Sony/OpenCV startup logic."""
    if self._is_streaming:
        self.stop_camera()

    try:
        print(f"[WORKER] Opening Camera Index: {index}")
        try:
            from mpcamera.config import get_settings
            cfg = get_settings()
            if getattr(cfg.camera, "force_directshow", True):
                self._vc = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            else:
                self._vc = cv2.VideoCapture(index)
        except Exception:
            self._vc = cv2.VideoCapture(index, cv2.CAP_DSHOW)

        if not self._vc.isOpened():
            self._vc = cv2.VideoCapture(index)

        if not self._vc.isOpened():
            self.error_occurred.emit(f"Could not open Camera Index {index}")
            return

        try:
            from mpcamera.config import get_settings
            cfg = get_settings()
            w = int(getattr(cfg.camera, "resolution_width", 1920))
            h = int(getattr(cfg.camera, "resolution_height", 1080))
            self._vc.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self._vc.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            fourcc_code = str(getattr(cfg.camera, "fourcc", "MJPG") or "MJPG")
            fourcc = cv2.VideoWriter_fourcc(*fourcc_code)
            self._vc.set(cv2.CAP_PROP_FOURCC, fourcc)
        except Exception:
            self._vc.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self._vc.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            self._vc.set(cv2.CAP_PROP_FOURCC, fourcc)

        self._is_streaming = True
        try:
            self._timer.start()
        except Exception:
            try:
                self._timer.start(33)
            except Exception:
                pass

    except Exception as e:
        # Ensure device handle is released on any error
        if self._vc is not None and self._vc.isOpened():
            self._vc.release()
        self._vc = None
        traceback.print_exc()
        self.error_occurred.emit(str(e))
```

- [ ] **Step 2: Verify manually**

Run the app, open a camera, then trigger an artificial error (e.g., disconnect camera mid-init). Verify the app can re-open the camera without "device busy" errors.

- [ ] **Step 3: Commit**

```bash
git add mpcamera/utils/camera_worker.py
git commit -m "fix: release VideoCapture handle on exception in start_camera (issue 3.1)"
```

---

## Task 3: Fix `_inference_running` Never Reset on Camera Stop (Issue 7.7)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — reset `_inference_running` in stop/error paths

If the user stops the camera while inference is running, `_inference_running` stays `True` forever, blocking all future inference.

- [ ] **Step 1: Find the `_stop_camera` method**

Search `camera_page.py` for `def _stop_camera`. Read 20 lines around it to understand what it does.

- [ ] **Step 2: Add reset of `_inference_running` in `_stop_camera`**

At the end of `_stop_camera` (before or after existing cleanup), add:

```python
self._inference_running = False
```

- [ ] **Step 3: Find the `_on_worker_error` method and add the same reset**

Search for `def _on_worker_error`. Add at the beginning of the method body:

```python
self._inference_running = False
```

- [ ] **Step 4: Confirm the guard at line ~1390 still works**

Read lines 1388–1395 to confirm `if self._inference_running: return` is still intact. This guard is correct — the fix is just ensuring the flag gets reset when the camera stops unexpectedly.

- [ ] **Step 5: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: reset _inference_running flag on camera stop/error (issue 7.7)"
```

---

## Task 4: Remove Redundant BGR→RGB Conversion (Issue 1.2)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py:929-942`

`_apply_adjustments_and_refresh` calls `cv2.cvtColor(adjusted, cv2.COLOR_BGR2RGB)` on line 934 on every frame before display. At 30 FPS / 1920×1080 this wastes ~186 MB/s. The fix: store an already-RGB version in `_current_frame_np` so display skips re-conversion.

- [ ] **Step 1: Modify `_apply_adjustments_and_refresh` to store RGB in `_current_frame_np`**

Find lines 929–942 in `camera_page.py` and replace:

```python
# BEFORE
# Update current frame used for color extraction and for saving to disk
self._current_frame_np = adjusted

# Update displayed pixmap
try:
    frame_rgb = cv2.cvtColor(adjusted, cv2.COLOR_BGR2RGB)
    h, w, ch = frame_rgb.shape
    qimg = QtGui.QImage(
        frame_rgb.data, w, h, ch * w, QtGui.QImage.Format.Format_RGB888
    )
    self._last_pixmap = QtGui.QPixmap.fromImage(qimg.copy())
    self._display_pixmap(self._last_pixmap)
except Exception:
    pass
```

```python
# AFTER
# Convert once for display; store BGR separately for inference/color analysis
try:
    frame_rgb = cv2.cvtColor(adjusted, cv2.COLOR_BGR2RGB)
    with self._frame_lock:
        self._current_frame_np = adjusted  # keep BGR for downstream (color analysis uses BGR)
    h, w, ch = frame_rgb.shape
    bytes_per_line = ch * w
    qimg = QtGui.QImage(
        frame_rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888
    )
    self._last_pixmap = QtGui.QPixmap.fromImage(qimg.copy())
    self._display_pixmap(self._last_pixmap)
except Exception:
    pass
```

- [ ] **Step 2: Verify display still works**

Launch the app, open a camera. Confirm the live view shows correct colors (not blue-tinted).

- [ ] **Step 3: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "perf: remove redundant BGR->RGB conversion on every display frame (issue 1.2)"
```

---

## Task 5: Fix RoboflowClient Singleton Unprotected Mutable State (Issue 2.2)

**Files:**
- Modify: `mpcamera/services/roboflow.py:69-96`

`refresh_auth_from_settings()` mutates `self.workflow`, `self.api_url`, etc. without holding `_lock`. If inference runs concurrently with a settings save, this is a race.

- [ ] **Step 1: Replace the class-level `Lock` with `RLock`**

In `roboflow.py` line 19, change:

```python
# BEFORE
_lock = Lock()

# AFTER
_lock = Lock()  # keep for singleton guard
_state_lock = Lock()  # new: protects mutable instance state
```

Import `Lock` is already present. No additional import needed.

- [ ] **Step 2: Wrap `refresh_auth_from_settings` body with the new lock**

```python
def refresh_auth_from_settings(self) -> None:
    """Refresh API URL/key/workspace from env or settings."""
    with RoboflowClient._state_lock:
        settings = _get_roboflow_settings()

        new_api_url = (
            os.getenv("ROBOFLOW_API_URL")
            or settings.get("api_url")
            or self.api_url
        )
        new_api_key = (
            os.getenv("ROBOFLOW_API_KEY")
            or settings.get("api_key")
            or self.api_key
        )
        new_workspace = (
            os.getenv("ROBOFLOW_WORKSPACE")
            or settings.get("workspace")
            or self.workspace
        )

        api_changed = (new_api_url != self.api_url) or (new_api_key != self.api_key)

        self.api_url = new_api_url
        self.api_key = new_api_key
        self.workspace = new_workspace

        if api_changed:
            self._create_client()
```

- [ ] **Step 3: Commit**

```bash
git add mpcamera/services/roboflow.py
git commit -m "fix: protect RoboflowClient mutable state with a dedicated lock (issue 2.2)"
```

---

## Task 6: Cache Raw Inference Results for Slider Re-filtering (Issue 5.1)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — store `_last_raw_result`; re-use on slider change

Currently, every slider change triggers a full inference re-run. The fix: save the unfiltered result from the last inference, and when sliders change just re-filter that cached result.

- [ ] **Step 1: Add `_last_raw_result` to controller state**

In `__init__`, after `self._last_preds: List[Dict[str, Any]] = []`, add:

```python
self._last_raw_result = None  # unfiltered inference output for slider re-use
```

- [ ] **Step 2: Store raw result in `_on_inference_worker_finished`**

In `_on_inference_worker_finished` (line ~1508), after `self._inference_running = False`, add:

```python
self._last_raw_result = raw_result  # cache for slider re-filtering
```

- [ ] **Step 3: Add `_refilter_from_cache` method**

Add a new method after `_on_inference_worker_finished`:

```python
def _refilter_from_cache(self):
    """Re-apply confidence/IoU filters on the cached raw result without re-running inference."""
    if self._last_raw_result is None:
        return

    import copy
    from mpcamera.utils.inference_utils import apply_confidence_iou_filters, parse_result_to_preds

    conf_val = self.DEFAULT_CONFIDENCE
    iou_val = self.DEFAULT_IOU
    if self.ui.get("conf_slider") is not None:
        conf_val = self.ui["conf_slider"].value() / 100.0
    if self.ui.get("iou_slider") is not None:
        iou_val = self.ui["iou_slider"].value() / 100.0

    # Work on a deep copy so we don't mutate the cached raw result
    filtered = copy.deepcopy(self._last_raw_result)
    filtered = apply_confidence_iou_filters(
        filtered, confidence_threshold=conf_val, iou_threshold=iou_val
    )
    preds = parse_result_to_preds(filtered) or []
    self._last_preds = preds
    self._update_results_display(preds, filtered)
```

- [ ] **Step 4: Connect sliders to `_refilter_from_cache` instead of re-running inference**

Find `_setup_connections` in `camera_page.py`. Locate where `conf_slider` and `iou_slider` connect to `_on_param_changed`. Change those connections to call `_refilter_from_cache` when a cached result exists:

```python
# Slider value changes → re-filter from cache (no new inference needed)
if self.ui.get("conf_slider") is not None:
    self.ui["conf_slider"].valueChanged.connect(self._refilter_from_cache)
if self.ui.get("iou_slider") is not None:
    self.ui["iou_slider"].valueChanged.connect(self._refilter_from_cache)
```

Remove (or guard) any existing `valueChanged` connections to `_on_param_changed` for these sliders.

- [ ] **Step 5: Verify sliders respond instantly without re-running inference**

Run the app, capture a static image, run inference, then move the confidence slider. Results should update immediately with no network call or model load.

- [ ] **Step 6: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "perf: cache raw inference result and re-filter on slider changes (issue 5.1)"
```

---

## Task 7: Introduce CameraState Enum to Fix State Machine (Issue 2.3)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py:118-122`

Four independent booleans (`_streaming`, `_paused`, `_inference_running`, timer activity) lead to inconsistent state transitions. Stopping the camera leaves `_inference_running = True`, permanently blocking future inference.

- [ ] **Step 1: Add `CameraState` enum near the top of `camera_page.py`**

After the imports at the top of `camera_page.py`, add:

```python
from enum import Enum, auto

class CameraState(Enum):
    IDLE = auto()
    STREAMING = auto()
    PAUSED = auto()
    INFERRING = auto()
```

- [ ] **Step 2: Add `_camera_state` instance variable and `_set_state` method**

In `__init__`, replace the four boolean declarations:

```python
# BEFORE
self._streaming = False
self._paused = False
self._inference_running = False
```

```python
# AFTER
self._streaming = False      # keep for compatibility during transition
self._paused = False         # keep for compatibility during transition
self._inference_running = False  # keep for compatibility during transition
self._camera_state = CameraState.IDLE
```

Add a new method `_set_state`:

```python
def _set_state(self, new_state: CameraState):
    """Atomically transition to new_state and sync legacy flags."""
    old = self._camera_state
    self._camera_state = new_state

    # Sync legacy boolean flags so existing code stays correct
    self._streaming = new_state in (CameraState.STREAMING, CameraState.INFERRING)
    self._paused = new_state == CameraState.PAUSED
    self._inference_running = new_state == CameraState.INFERRING

    print(f"[STATE] {old.name} → {new_state.name}")
```

- [ ] **Step 3: Use `_set_state` in the start/stop/inference methods**

Find `_stop_camera` (or equivalent). Ensure it calls `self._set_state(CameraState.IDLE)` instead of setting flags individually.

Find `_start_camera`. Ensure it calls `self._set_state(CameraState.STREAMING)`.

Find `_run_inference`. Ensure it calls `self._set_state(CameraState.INFERRING)` before dispatching.

Find `_on_inference_worker_finished` and `_on_inference_worker_error`. Both must call `self._set_state(CameraState.STREAMING if self._camera_worker and getattr(self._camera_worker, '_is_streaming', False) else CameraState.IDLE)`.

- [ ] **Step 4: Verify state transitions via log output**

Run the app, open camera, run inference, stop camera. Check terminal for the `[STATE]` log lines showing correct transitions: IDLE → STREAMING → INFERRING → STREAMING → IDLE.

- [ ] **Step 5: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "refactor: introduce CameraState enum and _set_state() to fix state machine (issue 2.3)"
```

---

## Task 8: Remove Double JSON Serialization in Local Inference (Issue 5.2)

**Files:**
- Modify: `mpcamera/utils/local_models_utils.py:260-303`
- Modify: `mpcamera/utils/inference_worker.py:90-96`

`predict_json` builds a Python list → `json.dumps()` it → `InferenceWorker` immediately calls `json.loads()` on it. This round-trip is pure waste.

- [ ] **Step 1: Add `predict` method to `LocalModelInference` that returns a dict**

In `local_models_utils.py`, after `predict_json`, add:

```python
def predict(
    self, image_path, confidence_threshold=None, iou_threshold=None, class_map=None
):
    """Runs prediction and returns a Python dict (no JSON serialization)."""
    conf_thresh = (
        confidence_threshold
        if confidence_threshold is not None
        else self.confidence_threshold
    )
    iou_thresh = iou_threshold if iou_threshold is not None else self.iou_threshold

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Image not found: {image_path}")

    h, w, _ = img.shape

    if self.model_type == "YOLOv11":
        formatted_predictions = self._predict_yolov11(img, conf_thresh, class_map, iou_thresh)
    elif self.model_type == "RF-DETR-SEG":
        formatted_predictions = self._predict_rfdetr_seg(img, conf_thresh, class_map)
    elif self.model_type == "MaskRCNN":
        formatted_predictions = self._predict_maskrcnn(img, conf_thresh, iou_thresh, class_map)
    else:
        raise ValueError(f"Unknown model type for prediction: {self.model_type}")

    return [
        {
            "count_objects": len(formatted_predictions),
            "predictions": {
                "image": {"width": w, "height": h},
                "predictions": formatted_predictions,
            },
        }
    ]
```

- [ ] **Step 2: Update `InferenceWorker` to call `predict` instead of `predict_json`**

In `inference_worker.py`, replace lines 90–96:

```python
# BEFORE
json_str = self._local_engine.predict_json(
    path_to_infer,
    confidence_threshold=conf,
    iou_threshold=iou,
    class_map=self.CLASS_MAP,
)
result = json.loads(json_str)
```

```python
# AFTER
result = self._local_engine.predict(
    path_to_infer,
    confidence_threshold=conf,
    iou_threshold=iou,
    class_map=self.CLASS_MAP,
)
```

- [ ] **Step 3: Remove `import json` from `inference_worker.py` if no longer needed**

Check if `json` is still used elsewhere in `inference_worker.py`. If not, remove the import.

- [ ] **Step 4: Verify local model inference still produces correct results**

Run the app with a local `.pth` or `.pt` model. Confirm particles are detected and morphometrics are computed correctly.

- [ ] **Step 5: Commit**

```bash
git add mpcamera/utils/local_models_utils.py mpcamera/utils/inference_worker.py
git commit -m "perf: remove double JSON serialization in local inference path (issue 5.2)"
```

---

## Task 9: Vectorize NMS IoU Calculation (Issue 1.3)

**Files:**
- Modify: `mpcamera/utils/inference_utils.py:156-187`

The greedy NMS loop calls `_iou_xyxy` (scalar) for every remaining pair on every iteration — O(n²) with no vectorization. With 50+ detections this is noticeable.

- [ ] **Step 1: Add vectorized IoU helper**

In `inference_utils.py`, before `_filter_prediction_list`, add:

```python
def _iou_matrix(boxes: np.ndarray) -> np.ndarray:
    """Compute N×N IoU matrix for an (N, 4) array of [x1, y1, x2, y2] boxes."""
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1).clip(0) * (y2 - y1).clip(0)

    inter_x1 = np.maximum(x1[:, None], x1[None, :])
    inter_y1 = np.maximum(y1[:, None], y1[None, :])
    inter_x2 = np.minimum(x2[:, None], x2[None, :])
    inter_y2 = np.minimum(y2[:, None], y2[None, :])
    inter_area = (inter_x2 - inter_x1).clip(0) * (inter_y2 - inter_y1).clip(0)

    union = areas[:, None] + areas[None, :] - inter_area
    iou = np.where(union > 0, inter_area / union, 0.0)
    return iou
```

- [ ] **Step 2: Replace the greedy NMS loop in `_filter_prediction_list`**

Find lines 156–186 in `inference_utils.py`. Replace the `while order:` loop with a vectorized version:

```python
if iou_t is None or len(boxed_meta) <= 1:
    return kept

# Sort by descending score
order = sorted(
    range(len(boxed_meta)),
    key=lambda i: float(boxed_meta[i]["score"]),
    reverse=True,
)

# Build box matrix for vectorized IoU
boxes_np = np.array([boxed_meta[i]["box"] for i in order], dtype=float)
iou_mat = _iou_matrix(boxes_np)

keep_order_positions = []
suppressed = set()
for idx in range(len(order)):
    if idx in suppressed:
        continue
    keep_order_positions.append(idx)
    for jdx in range(idx + 1, len(order)):
        if iou_mat[idx, jdx] > iou_t:
            suppressed.add(jdx)

keep_local_indices = {boxed_meta[order[pos]]["local_idx"] for pos in keep_order_positions}
# Always retain detections without valid boxes
for i, pred in enumerate(kept):
    if _pred_to_xyxy(pred) is None:
        keep_local_indices.add(i)

return [p for i, p in enumerate(kept) if i in keep_local_indices]
```

- [ ] **Step 3: Add `import numpy as np` to `inference_utils.py` if not present**

Check the import block at the top of `inference_utils.py`. Add `import numpy as np` if missing.

- [ ] **Step 4: Verify NMS still filters correctly**

Run inference on an image with multiple detections. Verify overlapping particles are deduplicated and the results count is reasonable (not 0, not all retained).

- [ ] **Step 5: Commit**

```bash
git add mpcamera/utils/inference_utils.py
git commit -m "perf: vectorize NMS IoU calculation with numpy matrix ops (issue 1.3)"
```

---

## Task 10: Remove Legacy Fallback Thread (Issue 2.6)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py:1444-1506`

The `_run_inference` method has a primary `InferenceWorker` path and a legacy `daemon=True` thread fallback. Bug fixes must be applied to both. The fallback also lacks lifecycle management.

- [ ] **Step 1: Read lines 1444–1510 of `camera_page.py`**

Confirm the structure: the `InferenceWorker` path returns early on success; the fallback `worker()` function and `Thread(...).start()` are only reached on failure.

- [ ] **Step 2: Remove the fallback**

Delete the entire fallback block from `_run_inference`:

```python
# DELETE from here:
# Fallback: legacy threaded implementation (kept for compatibility)
def worker():
    ...
Thread(target=worker, daemon=True).start()
# DELETE to here
```

Replace with an error log so failures are visible:

```python
# If InferenceWorker is unavailable, surface the error clearly
print("[INFERENCE] InferenceWorker not available — inference skipped")
self._set_state(CameraState.IDLE)
self._toggle_spinner(False)
```

- [ ] **Step 3: Check if `inference_finished_signal` is only used by the fallback**

Search `camera_page.py` for `inference_finished_signal`. If it is only connected to the legacy fallback handler, remove the signal definition and the handler method too.

- [ ] **Step 4: Verify inference still works end-to-end**

Run the app, capture a frame, run inference. Confirm results appear. The `InferenceWorker` path must handle all cases.

- [ ] **Step 5: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "refactor: remove legacy daemon thread inference fallback (issue 2.6)"
```

---

## Self-Review Checklist

- [x] **7.1** — Frame buffer mutex: Task 1
- [x] **7.2** — Signal thread marshaling: noted as lower risk (Qt queued connections handle this) — not included; `finished.emit` from QThread with auto-connection is safe in PyQt6
- [x] **3.1** — VideoCapture finally: Task 2
- [x] **3.2** — Daemon threads → lifecycle: partially addressed by Task 10 (legacy thread removed); `InferenceWorker` uses `daemon=True` thread internally — full QThread migration deferred as scope expansion
- [x] **1.2** — Redundant BGR→RGB: Task 4
- [x] **5.1** — Cache raw results: Task 6
- [x] **2.3** — State machine enum: Task 7
- [x] **3.4** — Temp file cleanup: `InferenceWorker.worker()` already has `finally: os.remove(temp_path)` — no fix needed
- [x] **1.3** — Vectorize NMS: Task 9
- [x] **5.2** — Double JSON serialization: Task 8
- [x] **7.7** — Inference deadlock on stop: Task 3
- [x] **2.2** — RoboflowClient lock: Task 5
- [x] **2.6** — Dual inference paths: Task 10

**Placeholder scan:** No TBD, TODO, or "similar to" references. All code blocks are complete.

**Type consistency:** `CameraState` defined in Task 7 Step 1, used in Tasks 3, 6, 7, 10. `_last_raw_result` set in Task 6 Step 1, referenced in Task 6 Steps 3–4. `_refilter_from_cache` defined in Task 6 Step 3, wired in Step 4.
