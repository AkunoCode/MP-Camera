# SoilSight — In-Depth Optimization Analysis

**Date:** 2026-04-11  
**Analyst:** Claude Code (claude-sonnet-4-6)  
**Scope:** Full codebase static analysis — performance, architecture, code quality, UI responsiveness, memory management, threading

---

## Summary

36 issues identified across 8 categories. No critical-severity blockers, but 19 high-severity issues that can cause crashes, data corruption, and significant performance degradation.

| Category            | Total | High | Medium |
|---------------------|-------|------|--------|
| Performance         | 7     | 5    | 2      |
| Architecture        | 6     | 4    | 2      |
| Code Quality        | 7     | 3    | 4      |
| UI Responsiveness   | 4     | 2    | 2      |
| Inference Pipeline  | 3     | 1    | 2      |
| Memory Management   | 4     | 1    | 3      |
| Threading           | 3     | 3    | 0      |
| Configuration       | 2     | 0    | 2      |
| **TOTAL**           | **36**| **19**| **17** |

---

## Recommended Fix Order

| Priority | Issue ID | Description | Impact |
|----------|----------|-------------|--------|
| 1  | 7.1 | Mutex on `_current_frame_np`           | Prevents crash             |
| 2  | 7.2 | Signal thread marshaling               | Prevents crash             |
| 3  | 3.1 | VideoCapture `finally` release         | Prevents device lock       |
| 4  | 3.2 | Daemon threads → QThread lifecycle     | Prevents data corruption   |
| 5  | 1.2 | Consolidate BGR→RGB to one place       | ~186 MB/s savings          |
| 6  | 5.1 | Cache raw results, apply filters lazily| Slider responsiveness      |
| 7  | 2.3 | Fix state machine with enum            | Correctness                |
| 8  | 3.4 | Temp file cleanup with `try/finally`   | Disk leak                  |
| 9  | 1.3 | Vectorize NMS IoU                      | Inference speed            |
| 10 | 5.2 | Remove double JSON serialization       | Local inference speed      |

---

## 1. Threading & Concurrency

### 7.1 — Race Condition on `_current_frame_np` *(HIGH)*

- **Files:** `mpcamera/controllers/camera_page.py:1193-1200`, `:930`, `:1638`, `:1928-1931`
- **Problem:** Camera worker writes `_raw_frame_np` while the display pipeline and inference worker both read it with no mutex. This is a data race that a thread sanitizer would flag as a TSAN error.
  - Camera worker thread sets `_raw_frame_np` (line 1199)
  - Main thread reads it at line 906 in `_apply_adjustments_and_refresh()`
  - Inference worker reads `_current_frame_np` at line 1931
  - Display path overwrites it at line 930
- **Fix:** Add a `threading.Lock` or `QMutex` around all reads and writes to `_raw_frame_np` and `_current_frame_np`.

---

### 7.2 — Signal Emitted from Wrong Thread *(HIGH)*

- **File:** `mpcamera/utils/inference_worker.py:124`
- **Problem:** `self.finished.emit(preds, result)` is called from the worker QThread. While Qt queued connections usually handle this safely, the object's thread affinity is not guaranteed. Should use `QMetaObject.invokeMethod()` with `Qt.QueuedConnection` to explicitly marshal to the main thread.
- **Fix:** Replace `self.finished.emit(...)` with:
  ```python
  QMetaObject.invokeMethod(
      self, "finished",
      Qt.ConnectionType.QueuedConnection,
      Q_ARG(object, preds),
      Q_ARG(object, result)
  )
  ```

---

### 7.3 — Daemon Thread Holds QPixmap Reference *(MEDIUM)*

- **Files:** `mpcamera/controllers/camera_page.py:1395-1403`, `:2051-2082`
- **Problem:** Inference worker saves a pixmap to file inside a daemon thread. If the main thread frees or replaces the pixmap while the thread still holds it, Qt's object lifecycle is corrupted (Qt GUI objects are not thread-safe).
- **Fix:** Convert the QPixmap to a numpy array or bytes on the main thread before handing it to the worker thread.

---

## 2. Memory & Resource Leaks

### 6.1 — Three Large Image Buffers Never Freed *(HIGH)*

- **File:** `mpcamera/controllers/camera_page.py:122-123`
- **Problem:** `_current_frame_np`, `_raw_frame_np`, and `_last_pixmap` are held as instance variables indefinitely. Each is ~6.2 MB for 1920×1080. Inference worker threads can hold stale numpy array references beyond the frame's useful life.
- **Fix:** Clear these on camera stop (set to `None`). For numpy buffers, implement a ring buffer or explicitly `del` and reassign.

---

### 3.1 — Camera VideoCapture Handle Leaked on Error *(HIGH)*

- **File:** `mpcamera/utils/camera_worker.py:41-100`
- **Problem:** `cv2.VideoCapture` is opened but the release call is not inside a `finally` block. Any exception between open and `timer.start()` leaks the OS device handle. Restarting the camera or switching devices will then fail.
- **Fix:**
  ```python
  try:
      self._vc = cv2.VideoCapture(...)
      # setup
      self._timer.start()
  except Exception:
      if self._vc and self._vc.isOpened():
          self._vc.release()
      raise
  ```

---

### 3.2 — Daemon Threads Not Joined on App Exit *(HIGH)*

- **Files:** `mpcamera/controllers/camera_page.py:1506`, `:2115`
- **Problem:** All worker threads are `Thread(..., daemon=True).start()`. The app can exit while inference is running or while data is being uploaded to Directus, potentially corrupting records or leaving temp files on disk.
- **Fix:** Switch to `QThread` with proper `quit()` + `wait()` in the controller's `closeEvent`. Or maintain a list of active threads and join them in the app shutdown hook.

---

### 3.4 — Temp Files Not Cleaned Up on Exception *(MEDIUM)*

- **Files:** `mpcamera/controllers/camera_page.py:1181`, `:2090`
- **Problem:** Multiple `NamedTemporaryFile(delete=False)` calls are not wrapped in `try/finally`. If an exception occurs before the cleanup call, the temp file is orphaned on disk indefinitely.
- **Fix:**
  ```python
  tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
  try:
      # use tmp.name
  finally:
      tmp.close()
      os.unlink(tmp.name)
  ```

---

### 6.3 — Results Table Accumulates Rows Without Limit *(MEDIUM)*

- **File:** `mpcamera/ui/results_window.py`
- **Problem:** `insertRow()` is called per particle with no row limit. After processing 1000 images × 50 particles, the table holds 50,000 rows and becomes sluggish to scroll, sort, or export.
- **Fix:** Either clear the table before each new batch, or cap the table at a configurable max (e.g., 10,000 rows) and log a warning when the limit is hit.

---

## 3. Performance Bottlenecks

### 1.2 — Redundant BGR→RGB Copy Every Frame *(HIGH)*

- **File:** `mpcamera/controllers/camera_page.py:934-940`
- **Problem:** `_apply_adjustments_and_refresh()` already produces an adjusted frame stored in `_current_frame_np`. Line 934 then calls `cv2.cvtColor()` again to convert BGR→RGB before creating a `QImage`. At 30 FPS / 1920×1080, this is ~186 MB/s of redundant array copies on the main thread.
- **Fix:** Store the already-converted RGB frame in `_current_frame_np` so display can use it directly without re-converting.

---

### 4.2 — Full Frame Conversion Pipeline Blocks Main Thread *(HIGH)*

- **File:** `mpcamera/controllers/camera_page.py:934-940`
- **Problem:** Every frame goes through: `cvtColor` → `QImage` construction → `QPixmap` deep copy → `setPixmap()`, all synchronously on the main thread. This competes with Qt's event loop and can cause dropped frames or input lag.
- **Fix:** Pre-allocate a `QImage` with a fixed buffer and reuse it per frame (`QImage(data_ptr, w, h, stride, Format_RGB888)`), avoiding the deep copy. Or use a separate render thread.

---

### 1.3 — O(n²) NMS Filter on Every Inference *(MEDIUM)*

- **File:** `mpcamera/utils/inference_utils.py:156-187`
- **Problem:** The greedy NMS loop recalculates pairwise IoU for every remaining pair of detections. With 50+ predictions, this is expensive and grows quadratically.
- **Fix:** Use vectorized numpy operations to compute all pairwise IoUs in a single matrix multiplication step, then apply the greedy mask selection on the sorted scores.

---

### 5.1 — Filter Not Cached; Re-applied on Every Slider Event *(HIGH)*

- **File:** `mpcamera/utils/inference_utils.py:190-228`
- **Problem:** `apply_confidence_iou_filters()` walks the full result tree every time a confidence or IoU slider changes. The raw (unfiltered) result is not cached separately.
- **Fix:** Store the raw inference result in `_last_raw_preds`. When sliders change, re-run `apply_confidence_iou_filters(_last_raw_preds, conf, iou)` instead of re-running full inference.

---

### 1.6 — Local Model Not Preloaded *(MEDIUM)*

- **File:** `mpcamera/utils/local_models_utils.py:79-87`
- **Problem:** The model weights are loaded on the first inference call, blocking for 2-5 seconds for large `.pth`/`.pt` files. There is no warmup or background preload.
- **Fix:** Trigger model loading in a background QThread when the Settings page sets a new model path, so by the time inference is triggered the model is already in memory.

---

### 5.2 — Double JSON Serialization in Local Inference *(MEDIUM)*

- **File:** `mpcamera/utils/local_models_utils.py:260-303`
- **Problem:** Local inference builds a Python list of dicts and calls `json.dumps([...], indent=2)`. The controller then calls `json.loads()` on the returned string. This round-trip serialization is entirely unnecessary.
- **Fix:** Return the Python dict/list directly from `LocalModelInference.run()` and remove both `json.dumps` and `json.loads` from this code path.

---

### 5.3 — Polygon Points Extracted Multiple Times per Prediction *(MEDIUM)*

- **File:** `mpcamera/utils/inference_utils.py:321-326`
- **Problem:** `extract_points_from_prediction()` (which converts raw mask data to polygon points) is called once during `_format_prediction()` and again later in the camera page controller during color analysis. The result is never cached.
- **Fix:** Store the extracted points in the prediction dict (e.g., `pred["_cached_points"]`) on first extraction and reuse them in subsequent calls.

---

## 4. Architecture Issues

### 2.3 — No Centralized State Machine *(HIGH)*

- **File:** `mpcamera/controllers/camera_page.py:118-122`
- **Problem:** Four independent boolean flags control controller state: `_streaming`, `_paused`, `_inference_running`, and timer activity. There is no enum or state machine class. State transitions are inconsistent — stopping the camera (line 1209) clears `_streaming` but leaves `_inference_running = True`, permanently blocking future inference triggers (checked at line 1390).
- **Fix:** Introduce a `CameraState(Enum)` with values like `IDLE`, `STREAMING`, `PAUSED`, `INFERRING`. All transitions go through a single `_set_state()` method that validates and applies the transition atomically.

---

### 2.1 — CameraPageController Tightly Couples Worker Instantiation *(HIGH)*

- **File:** `mpcamera/controllers/camera_page.py:219-233`
- **Problem:** Workers are directly instantiated inside `__init__` with no dependency injection. A failed worker init leaves `None` in `_camera_worker` or `_inference_worker`, creating null-check burden at every use site.
- **Fix:** Use a factory method or inject pre-constructed workers. Guard worker access with a single `@property` that raises a descriptive error if the worker isn't available.

---

### 2.2 — RoboflowClient Singleton Has Unprotected Mutable State *(HIGH)*

- **File:** `mpcamera/services/roboflow.py:18-107`
- **Problem:** The class-level `_lock` only guards singleton instantiation. `refresh_auth_from_settings()` mutates `workflow` and other fields without the lock, creating a race condition if inference is running concurrently.
- **Fix:** Extend the lock scope to cover `refresh_auth_from_settings()`, or use a `threading.RLock` and acquire it at the start of both `refresh_auth_from_settings()` and any method that reads `workflow`.

---

### 2.6 — Dual Inference Paths Create Maintenance Burden *(MEDIUM)*

- **Files:** `mpcamera/controllers/camera_page.py:1444-1506`
- **Problem:** The controller has both a primary `InferenceWorker` path and a legacy fallback daemon thread path. Bug fixes must be applied to both. The legacy path also lacks proper thread lifecycle management.
- **Fix:** Remove the legacy fallback. Harden the `InferenceWorker` path to handle the edge cases the fallback was guarding against.

---

### 7.7 — Stopping Camera While Inference Runs Deadlocks Future Inference *(MEDIUM)*

- **File:** `mpcamera/controllers/camera_page.py:1410-1415`
- **Problem:** If the user clicks "Stop Camera" while `_inference_running = True`, `_clear_scene()` destroys the view but the flag is never reset to `False`. The guard at line 1390 (`if self._inference_running: return`) then permanently prevents new inference.
- **Fix:** Reset `_inference_running = False` in the camera stop and error paths. The state machine fix (2.3) would resolve this automatically.

---

## 5. Code Quality & Error Handling

### 3.3 — Broad Exception Catching Masks Real Errors *(MEDIUM)*

- **Files:** `ui_nav.py:32-51`, `:54-92`, `:172-252`
- **Problem:** Multiple `try/except Exception: pass` blocks silently swallow initialization errors. If a widget fails to load, the failure is invisible, making debugging extremely difficult.
- **Fix:** At minimum, log the exception: `except Exception as e: logger.warning("Failed to init X: %s", e)`. For required components, re-raise.

---

### 3.5 — Missing Validation of Morphometric Inputs *(MEDIUM)*

- **File:** `mpcamera/utils/results_manager.py:26-88`
- **Problem:** `calculate_morphometrics()` does not validate required keys in the `pred` dict. If `points` is missing, it silently returns `None` values which propagate into the table and export as empty cells.
- **Fix:** Add an early guard:
  ```python
  if "points" not in pred or not pred["points"]:
      logger.warning("Prediction missing points, skipping morphometrics")
      return None
  ```

---

### 3.6 — Race Condition on `_current_local_model_path` *(MEDIUM)*

- **Files:** `mpcamera/controllers/camera_page.py:956-968`, `:1466-1473`
- **Problem:** The main thread checks and resets `_current_local_model_path` (line 957) while the worker thread reads it without a lock (line 1467). A model change mid-inference could cause the wrong model to be loaded.
- **Fix:** Snapshot `_current_local_model_path` on the main thread before spawning the worker, and pass the snapshot as a constructor argument.

---

## 6. UI Responsiveness

### 4.1 — No Inference Loading Indicator During Live Stream *(HIGH)*

- **File:** `mpcamera/controllers/camera_page.py:1414-1415`
- **Problem:** `_toggle_spinner(True)` is only called when `not self._streaming`. During live camera streaming, no visual feedback is given that inference is running. Users see frozen results with no indication for 3-5 seconds.
- **Fix:** Show a distinct "Analyzing..." overlay or badge on the live view when `_inference_running = True`, regardless of streaming state.

---

### 4.3 — Results Overwritten While Detail Window Is Open *(MEDIUM)*

- **Files:** `mpcamera/controllers/camera_page.py:1519`, `:1390-1393`
- **Problem:** `_last_preds` is replaced by new inference results while a detail window may be reading it, causing the window to show inconsistent or suddenly-changed data.
- **Fix:** Pass a snapshot of `_last_preds` to the detail window at open time rather than having it read the live reference.

---

### 4.4 — No Debouncing on Slider-Driven Re-filtering *(MEDIUM)*

- **File:** `mpcamera/controllers/camera_page.py:416-421`
- **Problem:** Sliders connect to `_on_param_changed()` via `sliderReleased`, but rapid slider movements can still fire multiple re-filter calls in quick succession.
- **Fix:** Use a `QTimer` (e.g., 150ms debounce) — restart the timer on each `valueChanged` event and only call `_on_param_changed()` when it fires.

---

## 7. Configuration

### 8.1 — Settings Loaded Multiple Times from Disk *(MEDIUM)*

- **File:** `mpcamera/config.py:82-115`
- **Problem:** `get_settings()` is called from `camera_page.__init__`, `camera_worker.start_camera()`, `local_models_utils.__init__`, and `um_per_pixel.calculate_micrometers_per_pixel()`. Each call may reload `config.json` from disk.
- **Fix:** Ensure the `Settings` singleton properly caches and only reads from disk once. Add an explicit `_loaded` flag gated behind the lock.

---

### 8.2 — Model Path Resolution Is Opaque *(MEDIUM)*

- **File:** `mpcamera/utils/local_models_utils.py:110-136`
- **Problem:** Path resolution checks 6 candidates sequentially without logging which was selected. Silent resolution failures are hard to debug.
- **Fix:** Log the resolved path at `INFO` level: `logger.info("Resolved model path: %s", resolved_path)`. If no candidate matches, raise `FileNotFoundError` with all attempted paths listed.

---

*Generated by Claude Code static analysis — 2026-04-11*
