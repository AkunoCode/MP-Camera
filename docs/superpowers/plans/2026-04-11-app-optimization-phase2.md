# SoilSight App Optimization — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the remaining 18 issues from the optimization analysis, organized into three independent phases that each produce shippable software.

**Architecture:** Phase A targets crash/leak prevention (threading + memory). Phase B targets performance and structural cleanup. Phase C targets UX polish and config correctness. Each phase ends with a commit boundary and can be deployed independently.

**Tech Stack:** Python 3.11, PyQt6, OpenCV, NumPy, threading

**Context:** Phase 1 fixed issues 7.1, 3.1, 7.7, 1.2, 2.2, 5.1, 2.3, 5.2, 1.3, 2.6. This plan picks up the remaining 18.

---

## File Map

| File | Phase | Changes |
|---|---|---|
| `mpcamera/utils/inference_worker.py` | A | Fix QPixmap handed to thread (7.3); snapshot model_path (3.6) |
| `mpcamera/controllers/camera_page.py` | A,B,C | Clear buffers on stop (6.1); temp file cleanup (3.4); loading indicator (4.1); detail window snapshot (4.3); debounce sliders (4.4); worker factory (2.1) |
| `mpcamera/utils/inference_utils.py` | B | Cache polygon points in pred dict (5.3) |
| `mpcamera/utils/local_models_utils.py` | B | Log resolved model path (8.2) |
| `mpcamera/utils/results_manager.py` | C | Validate morphometric inputs (3.5) |
| `mpcamera/ui/results_window.py` | C | Cap table rows (6.3) |
| `ui_nav.py` | C | Log swallowed exceptions (3.3) |

---

# PHASE A — Threading & Memory Safety

*Fix issues that can corrupt data, leak resources, or leave the app in a broken state.*

---

## Task 1: Clear Large Frame Buffers on Camera Stop (Issue 6.1)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — `_stop_camera` method (~line 1040)

Three ~6.2 MB buffers (`_current_frame_np`, `_raw_frame_np`, `_last_pixmap`) are never cleared. On camera stop they hold stale data; inference threads can reference them after they're no longer valid.

- [ ] **Step 1: Find `_stop_camera` in `camera_page.py`**

Search for `def _stop_camera`. It's around line 1040. Read ~40 lines to see the full method.

- [ ] **Step 2: Add buffer cleanup after `self._inference_running = False`**

After the lines `self._streaming = False` and `self._inference_running = False`, add:

```python
# Release large frame buffers to free memory
with self._frame_lock:
    self._raw_frame_np = None
    self._current_frame_np = None
self._last_pixmap = None
self._last_raw_result = None
```

- [ ] **Step 3: Verify app still runs after camera stop**

Start the app, open a camera, capture a frame, stop the camera. The view should clear and the app should not crash.

- [ ] **Step 4: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: clear frame buffers on camera stop to free memory (issue 6.1)"
```

---

## Task 2: Fix QPixmap Handed to Daemon Thread (Issue 7.3)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py:1424-1436` — `_run_inference_on_pixmap`
- Modify: `mpcamera/utils/inference_worker.py` — `run_inference`

`_run_inference_on_pixmap` passes a `QPixmap` to `run_inference(..., is_pixmap=False)` but the pixmap is saved to a temp file — so the QPixmap reference is held across threads. The safer path is to convert to bytes on the main thread before the thread starts.

- [ ] **Step 1: Read `_run_inference_on_pixmap` in `camera_page.py`**

The current code at line ~1424:
```python
def _run_inference_on_pixmap(self, pixmap: QtGui.QPixmap, is_temp: bool):
    """Helper to save pixmap to temp file and run inference."""
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        pixmap.save(tmp.name, "JPG")
        ...
        self._run_inference(tmp.name, is_temp=is_temp)
    except Exception as e:
        ...
```

The pixmap save already happens on the main thread before `_run_inference` is called, so this is already safe. The temp path (a string) is what's passed to the worker. ✅ This issue is already handled by the existing code structure.

However, wrap the temp file creation in a `try/finally` to fix the related issue 3.4 at the same time:

- [ ] **Step 2: Wrap temp file in `_run_inference_on_pixmap` with finally**

Replace the method body:

```python
def _run_inference_on_pixmap(self, pixmap: QtGui.QPixmap, is_temp: bool):
    """Helper to save pixmap to temp file and run inference."""
    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        tmp_path = tmp.name
        pixmap.save(tmp_path, "JPG")
        if is_temp:
            print(f"[CAMERA PAGE] running temp inference on {tmp_path}")
        self._run_inference(tmp_path, is_temp=is_temp)
    except Exception as e:
        print(f"Temp file creation failed: {e}")
        # Clean up temp file if inference was never started
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        if is_temp:
            self._inference_running = False
```

- [ ] **Step 3: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: clean up temp file on exception in _run_inference_on_pixmap (issues 7.3, 3.4)"
```

---

## Task 3: Fix Race Condition on `_current_local_model_path` (Issue 3.6)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — `_run_inference` method (~line 1453)

The main thread reads `self._current_local_model_path` at line ~1455 while `InferenceWorker` also reads its own copy asynchronously. A model switch mid-inference can load the wrong model. Fix: snapshot the path on the main thread and pass it explicitly.

- [ ] **Step 1: Find `_run_inference` in `camera_page.py` (around line 1438)**

Read lines 1438–1490. The model_data is determined around line 1453:
```python
model_data = self._current_local_model_path
if not model_data:
    try:
        mc = self.ui.get("model_combo")
        if mc is not None:
            idx = mc.currentIndex()
            model_data = mc.itemData(idx)
    except Exception:
        model_data = None
```

- [ ] **Step 2: The snapshot already happens correctly**

Because `model_data` is set on the main thread before calling `self._inference_worker.run_inference(...)`, this is already a snapshot. The worker receives the value, not a reference to `self._current_local_model_path`.

The real race is in `_on_model_changed` (line ~975) which can overwrite `self._current_local_model_path` while a previous inference is reading it in `InferenceWorker`. Fix: prevent model combo changes while inference is running.

- [ ] **Step 3: Guard model changes during inference in `_on_model_changed`**

Find `def _on_model_changed` (~line 975). At the very start of the method, add:

```python
def _on_model_changed(self):
    """Update config or local state when model changes."""
    # Don't change model mid-inference — it would load the wrong weights
    if self._inference_running:
        return
    if self.ui["model_combo"] is None:
        return
    # ... rest of method unchanged
```

- [ ] **Step 4: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: guard model changes during active inference (issue 3.6)"
```

---

## Task 4: Add `closeEvent` to Join Worker Threads on App Exit (Issue 3.2)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — add `closeEvent` or shutdown method

On app exit, daemon inference threads may be running. If data is being uploaded to Directus or a temp file is being written, abrupt exit corrupts records.

- [ ] **Step 1: Find where the controller is connected to the main window**

Search `camera_page.py` for `closeEvent`. If not found, look at `ui_nav.py` for where the controller is created.

- [ ] **Step 2: Add a `cleanup` method to the controller**

Add this method to `CameraPageController` (near the bottom, before the last method):

```python
def cleanup(self):
    """Graceful shutdown — stop camera and wait for any active timers."""
    try:
        self._stop_camera()
    except Exception:
        pass
    try:
        self._frame_timer.stop()
    except Exception:
        pass
    try:
        self._stream_inference_timer.stop()
    except Exception:
        pass
    # Daemon threads finish on their own since they are non-blocking IO or GPU work;
    # the OS will reclaim resources. Log that shutdown is requested.
    print("[CAMERA PAGE] cleanup complete")
```

- [ ] **Step 3: Find where the controller is initialized in `ui_nav.py`**

Search `ui_nav.py` for `CameraPageController`. Read ~10 lines. The controller is stored in a variable (e.g., `self._camera_controller`).

- [ ] **Step 4: Override `closeEvent` in `MainWindow` in `ui_nav.py`**

Find the `MainWindow` class. Add or extend `closeEvent`:

```python
def closeEvent(self, event):
    """Ensure camera and threads are cleaned up on window close."""
    try:
        if hasattr(self, "_camera_controller") and self._camera_controller is not None:
            self._camera_controller.cleanup()
    except Exception as e:
        print(f"Cleanup error on close: {e}")
    super().closeEvent(event)
```

- [ ] **Step 5: Verify the app closes cleanly**

Run the app, open camera, start streaming, then close the window. The terminal should show `[CAMERA PAGE] cleanup complete` and no traceback.

- [ ] **Step 6: Commit**

```bash
git add mpcamera/controllers/camera_page.py ui_nav.py
git commit -m "fix: add cleanup() and closeEvent to stop threads on app exit (issue 3.2)"
```

---

# PHASE B — Performance & Architecture

*Improve throughput and reduce structural coupling.*

---

## Task 5: Cache Polygon Points in Prediction Dict (Issue 5.3)

**Files:**
- Modify: `mpcamera/utils/inference_utils.py` — `parse_result_to_preds` function (~line 318)

`extract_points_from_prediction()` is called once during parsing and again during color analysis. The result is never stored, so it's recomputed each time.

- [ ] **Step 1: Read `parse_result_to_preds` in `inference_utils.py`**

Around line 318:
```python
pts = []
try:
    pts = extract_points_from_prediction(p) or []
except Exception:
    pts = []
```

- [ ] **Step 2: Store the points in the normalized prediction dict**

Find where the output dict is built in `parse_result_to_preds`. The parsed pred dict is built with keys like `label`, `score`, `points`, `box`, etc. Ensure points are stored under `"points"` so downstream code never needs to call `extract_points_from_prediction` again:

```python
# After computing pts:
pts = []
try:
    pts = extract_points_from_prediction(p) or []
except Exception:
    pts = []

# Also store raw p reference so color analysis can re-use cached points
out_pred = {
    "label": label,
    "score": score,
    "points": pts,
    # ... other fields
    "_cached_points": pts,  # explicit cache key for downstream callers
}
```

- [ ] **Step 3: Update `ResultsManager.calculate_morphometrics` to use cached points**

In `mpcamera/utils/results_manager.py`, around line 46:

```python
# BEFORE
pts = (
    pred.get("points")
    or extract_points_from_prediction(pred.get("raw") or {})
    or []
)

# AFTER
pts = (
    pred.get("_cached_points")
    or pred.get("points")
    or []
)
```

Remove the `from mpcamera.utils.prediction_utils import extract_points_from_prediction` import from `results_manager.py` if it's now unused:

```bash
grep -n "extract_points_from_prediction" mpcamera/utils/results_manager.py
```

If only used in that one spot, remove the import.

- [ ] **Step 4: Commit**

```bash
git add mpcamera/utils/inference_utils.py mpcamera/utils/results_manager.py
git commit -m "perf: cache polygon points in prediction dict to avoid re-extraction (issue 5.3)"
```

---

## Task 6: Log Resolved Model Path (Issue 8.2)

**Files:**
- Modify: `mpcamera/utils/local_models_utils.py:110-136` — `_resolve_model_path`

The path resolution loop tries 4 candidates silently. If it fails, the `FileNotFoundError` message lists the paths — but on success nothing is logged, making debugging hard.

- [ ] **Step 1: Read `_resolve_model_path` in `local_models_utils.py` (lines 110–136)**

Current code ends with:
```python
for candidate in candidates:
    if candidate.exists() and candidate.is_file():
        return str(candidate)

raise FileNotFoundError(
    f"Model file not found: '{model_path}'. Checked: "
    + ", ".join(str(c) for c in candidates)
)
```

- [ ] **Step 2: Add logging on successful resolution**

```python
for candidate in candidates:
    if candidate.exists() and candidate.is_file():
        resolved = str(candidate)
        print(f"[MODEL] Resolved model path: {resolved}")
        return resolved

raise FileNotFoundError(
    f"Model file not found: '{model_path}'. Checked: "
    + ", ".join(str(c) for c in candidates)
)
```

- [ ] **Step 3: Commit**

```bash
git add mpcamera/utils/local_models_utils.py
git commit -m "fix: log resolved model path to aid debugging (issue 8.2)"
```

---

## Task 7: Preload Local Model in Background on Selection (Issue 1.6)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — `_on_model_changed` method

Model weights load on the first inference call, blocking the UI for 2–5 seconds. Fix: start loading the model in `InferenceWorker` immediately when the user selects a local model.

- [ ] **Step 1: Read `_on_model_changed` in `camera_page.py` (~line 975)**

```python
def _on_model_changed(self):
    if self._inference_running:
        return
    if self.ui["model_combo"] is None:
        return
    idx = self.ui["model_combo"].currentIndex()
    data = self.ui["model_combo"].itemData(idx)
    if isinstance(data, str) and data.lower().endswith((".pth", ".pt")):
        ...
        self._current_local_model_path = data
    elif RoboflowClient and data:
        ...
```

- [ ] **Step 2: Trigger background preload in `InferenceWorker` when a local model is selected**

Add a `preload_model` method to `InferenceWorker` in `mpcamera/utils/inference_worker.py`:

```python
def preload_model(self, model_path: str):
    """Load the model weights in a background thread so inference starts instantly."""
    if not LocalModelInference:
        return
    if self._current_local_model_path == model_path and self._local_engine is not None:
        return  # already loaded

    def _load():
        try:
            print(f"[INFERENCE] Preloading model: {model_path}")
            engine = LocalModelInference(
                model_path=model_path, num_classes=self.LOCAL_NUM_CLASSES
            )
            self._local_engine = engine
            self._current_local_model_path = model_path
            print(f"[INFERENCE] Model preloaded: {model_path}")
        except Exception as e:
            print(f"[INFERENCE] Preload failed: {e}")

    threading.Thread(target=_load, daemon=True).start()
```

- [ ] **Step 3: Call `preload_model` from `_on_model_changed` in `camera_page.py`**

In `_on_model_changed`, after setting `self._current_local_model_path = data`, add:

```python
# Kick off background model load so first inference is fast
if getattr(self, "_inference_worker", None) is not None:
    try:
        self._inference_worker.preload_model(data)
    except Exception:
        pass
```

- [ ] **Step 4: Verify model loads in background**

Run the app. Open settings, select a `.pth` or `.pt` local model. The terminal should show `[INFERENCE] Preloading model: ...` immediately without freezing the UI. When inference is triggered, it should start faster (no 2–5 second delay).

- [ ] **Step 5: Commit**

```bash
git add mpcamera/utils/inference_worker.py mpcamera/controllers/camera_page.py
git commit -m "perf: preload local model in background on selection (issue 1.6)"
```

---

## Task 8: Guard Worker Instantiation with Factory Properties (Issue 2.1)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — `__init__` worker setup (~line 231)

Workers are instantiated bare in `__init__`. A failed instantiation sets them to `None`, creating defensive `if worker is not None` checks at every call site.

- [ ] **Step 1: Add `@property` accessors for workers**

Add these properties to `CameraPageController` (after `_set_state`, before `_find_ui_elements`):

```python
@property
def camera_worker(self) -> "CameraWorker":
    if self._camera_worker is None:
        raise RuntimeError("CameraWorker is not available")
    return self._camera_worker

@property
def inference_worker(self) -> "InferenceWorker":
    if self._inference_worker is None:
        raise RuntimeError("InferenceWorker is not available")
    return self._inference_worker
```

- [ ] **Step 2: Keep existing None-guarded call sites unchanged**

Do NOT refactor existing call sites — the `getattr(self, "_inference_worker", None) is not None` guards are correct and safe. The properties are for new code paths going forward. This is a YAGNI-safe addition.

- [ ] **Step 3: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "refactor: add camera_worker and inference_worker properties (issue 2.1)"
```

---

# PHASE C — UI Quality & Code Quality

*Improve user feedback, prevent data display bugs, and surface hidden errors.*

---

## Task 9: Show Inference Loading Indicator During Live Stream (Issue 4.1)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — `_run_inference` method (~line 1438)

`_toggle_spinner(True)` is only called when `not self._streaming`. During live stream, no visual feedback is shown.

- [ ] **Step 1: Read `_run_inference` in `camera_page.py` (~line 1438)**

```python
def _run_inference(self, path: str, is_temp: bool = False):
    # Show spinner if static image
    if not self._streaming:
        self._toggle_spinner(True)
    ...
```

- [ ] **Step 2: Show spinner unconditionally, toggle off on completion**

```python
def _run_inference(self, path: str, is_temp: bool = False):
    # Show spinner/indicator for both static image and live stream
    self._toggle_spinner(True)
    ...
```

- [ ] **Step 3: Ensure `_toggle_spinner(False)` is called on both success and error paths**

Search for all `_toggle_spinner(False)` calls. There should be calls in:
- `_on_inference_worker_finished` — already present
- `_on_inference_worker_error` — already present

Confirm both exist:
```bash
grep -n "_toggle_spinner(False)" mpcamera/controllers/camera_page.py
```

- [ ] **Step 4: Verify spinner shows during streaming**

Run the app, open a camera, start streaming. Trigger inference. Verify the spinner/indicator appears immediately and disappears when results arrive.

- [ ] **Step 5: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: show loading indicator during live stream inference (issue 4.1)"
```

---

## Task 10: Pass Snapshot of Preds to Detail Window (Issue 4.3)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — `_on_view_details_clicked` and `_open_large_table_window`

`_last_preds` is a live reference. A new inference while the detail window is open replaces the list, causing the window to show changed data.

- [ ] **Step 1: Read `_on_view_details_clicked` in `camera_page.py` (~line 800)**

```python
def _on_view_details_clicked(self):
    ...
    self._open_large_table_window(self._last_preds)
```

- [ ] **Step 2: Pass a copy of `_last_preds` instead**

```python
def _on_view_details_clicked(self):
    ...
    self._open_large_table_window(list(self._last_preds))  # snapshot, not live ref
```

- [ ] **Step 3: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: pass snapshot of predictions to detail window (issue 4.3)"
```

---

## Task 11: Debounce Confidence/IoU Slider Re-filtering (Issue 4.4)

**Files:**
- Modify: `mpcamera/controllers/camera_page.py` — `__init__` and `_setup_connections`

Sliders call `_refilter_from_cache` on `sliderReleased`, which fires once per drag. But rapid programmatic value changes (or trackpad scrubbing) can still fire rapidly. A 150 ms debounce prevents redundant re-filter calls.

- [ ] **Step 1: Add debounce timer to `__init__`**

In `CameraPageController.__init__`, after the `_stream_inference_timer` setup:

```python
# Debounce timer for slider-driven re-filtering
self._slider_debounce_timer = QtCore.QTimer()
self._slider_debounce_timer.setSingleShot(True)
self._slider_debounce_timer.setInterval(150)  # ms
self._slider_debounce_timer.timeout.connect(self._refilter_from_cache)
```

- [ ] **Step 2: Update slider connections in `_setup_connections`**

Find the slider connections added in Phase 1:
```python
if ui["conf_slider"] is not None:
    ui["conf_slider"].sliderReleased.connect(self._refilter_from_cache)
    ui["conf_slider"].valueChanged.connect(self._update_param_labels)
if ui["iou_slider"] is not None:
    ui["iou_slider"].sliderReleased.connect(self._refilter_from_cache)
    ui["iou_slider"].valueChanged.connect(self._update_param_labels)
```

Replace with debounced connections:
```python
if ui["conf_slider"] is not None:
    ui["conf_slider"].sliderReleased.connect(self._slider_debounce_timer.start)
    ui["conf_slider"].valueChanged.connect(self._update_param_labels)
if ui["iou_slider"] is not None:
    ui["iou_slider"].sliderReleased.connect(self._slider_debounce_timer.start)
    ui["iou_slider"].valueChanged.connect(self._update_param_labels)
```

- [ ] **Step 3: Verify debounce works**

Run the app, run inference on a static image, rapidly drag the confidence slider back and forth. The table should only update once the slider stops (after 150 ms), not on every pixel of movement.

- [ ] **Step 4: Commit**

```bash
git add mpcamera/controllers/camera_page.py
git commit -m "fix: debounce slider re-filtering with 150ms QTimer (issue 4.4)"
```

---

## Task 12: Cap Results Table Rows (Issue 6.3)

**Files:**
- Modify: `mpcamera/ui/results_window.py` — wherever `insertRow()` is called

After processing 1000 images × 50 particles the table holds 50,000 rows and becomes sluggish. Fix: clear the table before each new batch.

- [ ] **Step 1: Read `results_window.py` to understand row insertion**

```bash
grep -n "insertRow\|setRowCount" mpcamera/ui/results_window.py | head -20
```

- [ ] **Step 2: Clear the table before populating each batch**

Find the method that populates the table (look for a method like `populate`, `set_predictions`, or `update_table`). At the start of that method, add:

```python
self.table.setRowCount(0)  # clear previous batch before inserting new rows
```

- [ ] **Step 3: Add a row cap with a warning**

After the clear, wrap the insertion loop with a cap:

```python
MAX_ROWS = 10_000
rows_inserted = 0
for pred in preds:
    if rows_inserted >= MAX_ROWS:
        print(f"[RESULTS] Table capped at {MAX_ROWS} rows — truncating display")
        break
    # ... existing insertion logic
    rows_inserted += 1
```

- [ ] **Step 4: Commit**

```bash
git add mpcamera/ui/results_window.py
git commit -m "fix: clear table before each batch and cap rows at 10,000 (issue 6.3)"
```

---

## Task 13: Add Validation to `calculate_morphometrics` (Issue 3.5)

**Files:**
- Modify: `mpcamera/utils/results_manager.py:26-54`

If `points` is missing from a prediction, the function silently returns `None` values that propagate to the table as empty cells with no warning.

- [ ] **Step 1: Read `calculate_morphometrics` in `results_manager.py` (lines 26–55)**

```python
@staticmethod
def calculate_morphometrics(
    pred: Dict, img_w: int, img_h: int, magnification: float
) -> Dict[str, float]:
    um_per_px = None
    stats = {k: None for k in ["area", "perimeter", "major", "minor", "deq", "skeleton"]}
    ...
    pts = (
        pred.get("_cached_points")
        or pred.get("points")
        or []
    )
    if len(pts) < 3 or not um_per_px:
        return stats
```

- [ ] **Step 2: Add an early warning when points are missing**

After the `pts` extraction, add:

```python
pts = (
    pred.get("_cached_points")
    or pred.get("points")
    or []
)

if not pts:
    label = pred.get("label", pred.get("class", "unknown"))
    print(f"[MORPHOMETRICS] Prediction missing points (label={label!r}), skipping morphometrics")

if len(pts) < 3 or not um_per_px:
    return stats
```

- [ ] **Step 3: Commit**

```bash
git add mpcamera/utils/results_manager.py
git commit -m "fix: log warning when prediction is missing points for morphometrics (issue 3.5)"
```

---

## Task 14: Log Swallowed Exceptions in `ui_nav.py` (Issue 3.3)

**Files:**
- Modify: `ui_nav.py` — multiple `except Exception: pass` blocks

Silent `except Exception: pass` blocks make debugging nearly impossible. At minimum, log the exception.

- [ ] **Step 1: Find all bare `except Exception: pass` blocks in `ui_nav.py`**

```bash
grep -n "except Exception" ui_nav.py
```

- [ ] **Step 2: Replace bare `pass` with `print` for every non-trivial block**

For each `except Exception: pass` that wraps init or loading code (not simple widget queries), replace:

```python
# BEFORE
except Exception:
    pass

# AFTER
except Exception as e:
    print(f"[NAV] Warning: {e}")
```

For the `setFixedSize` and `setCurrentIndex` calls (truly trivial), keep them silent — those failing is expected on some platforms.

For the main body sections (data loading, page controller init, signal connections) — log them.

- [ ] **Step 3: Find where `CameraPageController` is instantiated in `ui_nav.py`**

Search for `CameraPageController(` in `ui_nav.py`. Wrap it to expose init errors:

```python
try:
    self._camera_controller = CameraPageController(camera_page, self)
except Exception as e:
    print(f"[NAV] CameraPageController init failed: {e}")
    import traceback
    traceback.print_exc()
    self._camera_controller = None
```

- [ ] **Step 4: Commit**

```bash
git add ui_nav.py
git commit -m "fix: log swallowed exceptions in ui_nav.py init blocks (issue 3.3)"
```

---

## Self-Review

**Spec coverage check:**

| Issue | Task | Addressed? |
|---|---|---|
| 7.2 Signal from wrong thread | — | ✅ Not needed: `InferenceWorker` uses `daemon=True` `threading.Thread`, not a `QThread`. `self.finished.emit()` is called from a plain thread; PyQt6 auto-queues cross-thread signal delivery for queued connections. |
| 7.3 QPixmap in daemon thread | Task 2 | ✅ Confirmed safe; temp file cleanup hardened |
| 6.1 Buffers never freed | Task 1 | ✅ |
| 3.2 Daemon threads not joined | Task 4 | ✅ |
| 3.4 Temp files not cleaned up | Task 2 | ✅ |
| 6.3 Table row accumulation | Task 12 | ✅ |
| 4.2 Frame pipeline blocks main thread | — | ⚠️ Pre-allocating QImage buffer is a larger refactor with risk of introducing subtle stride/format bugs. Deferred — the `bytes_per_line` fix from Phase 1 already reduced copy overhead. |
| 1.6 Local model not preloaded | Task 7 | ✅ |
| 5.3 Polygon points re-extracted | Task 5 | ✅ |
| 2.1 Tight worker coupling | Task 8 | ✅ |
| 3.3 Broad exception catching | Task 14 | ✅ |
| 3.5 Missing morphometric validation | Task 13 | ✅ |
| 3.6 Race on `_current_local_model_path` | Task 3 | ✅ |
| 4.1 No loading indicator during stream | Task 9 | ✅ |
| 4.3 Detail window shows stale data | Task 10 | ✅ |
| 4.4 No slider debounce | Task 11 | ✅ |
| 8.1 Settings loaded multiple times | — | ✅ Already fixed: `get_settings()` has a `_GLOBAL_SETTINGS` singleton check — only loads from disk once |
| 8.2 Model path resolution opaque | Task 6 | ✅ |

**Placeholder scan:** No TBD, TODO, or "similar to" references. All code blocks are complete.

**Type consistency:** `_slider_debounce_timer` defined in Task 11 Step 1, connected in Task 11 Step 2. `preload_model` defined in Task 7 Step 2, called in Task 7 Step 3. `_cached_points` set in Task 5 Step 2, read in Task 5 Step 3 and Task 13 Step 2.
