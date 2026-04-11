# Comprehensive Logging Sweep — Design Spec

**Date:** 2026-04-11  
**Status:** Approved

## Goal

Make every failure in SoilSight visible in `~/.mpcamera/debug.log`. Two root problems to fix:

1. **Silent exception blocks** — bare `except Exception:` that swallow errors with no trace
2. **Thin context** — key pipeline events (inference trigger, model load, Directus upload) have no log entry, making it impossible to reconstruct what was happening when a failure occurred

## Approach

Targeted sweep across 8 files. No new infrastructure — the existing `logging.getLogger(__name__)` pattern and `setup_logging()` from `mpcamera/logging_utils.py` remain unchanged. Work falls into three categories.

---

## Category 1: Silent Exception Blocks

Every bare `except Exception:` that currently does nothing gets a log call. Severity depends on context:

- **`logger.error(..., exc_info=True)`** — for failures that impact functionality (inference, upload, morphometrics)
- **`logger.warning(...)`** — for degraded-but-continuing situations (optional feature unavailable, fallback used)
- **`logger.debug(...)`** — for optional import fallbacks that are expected to fail in some environments

### Files and approximate block counts

| File | Silent blocks | Notes |
|---|---|---|
| `mpcamera/controllers/camera_page.py` | ~40 | Highest priority — core inference pipeline |
| `mpcamera/ui/zoomable_view.py` | ~22 | UI rendering; use `logger.warning` (non-critical) |
| `mpcamera/ui/results_window.py` | ~12 | Results display and Directus upload path |
| `mpcamera/utils/inference_utils.py` | ~11 | Prediction parsing; each block needs context on what failed |
| `mpcamera/services/roboflow.py` | ~3 | Import fallback + client errors |
| `mpcamera/services/directus.py` | ~2 | API call failures |
| `mpcamera/config.py` | ~4 | Config load/validation failures |

### Severity guide for exception blocks

```
Optional import at module top level     → logger.debug("Optional import X unavailable: {e}")
Fallback path taken (still works)       → logger.warning("...; falling back to Y", exc_info=True)
Failure that breaks a feature           → logger.error("...", exc_info=True)
```

---

## Category 2: Replace `print()` Calls

| File | Line | Current | Replacement |
|---|---|---|---|
| `results_window.py` | 185 | `print("[RESULTS] Table capped...")` | `logger.warning("Table capped at {MAX_ROWS} rows — truncating display")` |
| `results_window.py` | 303 | `print(f"Error deleting row: {e}")` | `logger.error("Error deleting row", exc_info=True)` |
| `results_window.py` | 315 | `print(f"Updating {n} records...")` | `logger.info(f"Uploading {n} morphometric records to Directus")` |
| `roboflow.py` | 71 | `print("RoboflowClient: failed...")` | `logger.error("Failed to create RoboflowClient", exc_info=True)` |
| `config.py` | 105 | `print(...)` to stderr | `logger.warning(...)` |
| `config.py` | 118 | `print(f"Config validation warning: {e.message}")` | `logger.warning(f"Config validation: {e.message}")` |

---

## Category 3: Structured Boundary Log Lines

Add `logger.info()` / `logger.debug()` at pipeline entry and exit points that currently log nothing. These lines allow reconstructing the exact state when a failure occurs.

### `camera_page.py` — inference pipeline

```python
# Inference trigger
logger.info(f"Inference triggered: model={model_type}, sample={sample_id}, frame={frame.shape}")

# Inference result
logger.info(f"Inference complete: {len(predictions)} particles detected")

# Per-particle morphometrics
logger.debug(f"Computing morphometrics for particle {i}: class={label}, mask_pts={len(points)}")
```

### `local_models_utils.py` — model loading

```python
logger.info(f"Loading model from {path}")
logger.info(f"Model loaded: architecture={arch}, device={device}")
logger.error(f"Failed to load model from {path}", exc_info=True)
```

### `directus.py` — API calls

```python
logger.info(f"Uploading {count} records to Directus collection '{collection}'")
logger.info(f"Directus upload complete: {count} records")
logger.error(f"Directus upload failed for collection '{collection}'", exc_info=True)
```

### `inference_utils.py` — parsing and filtering

```python
logger.debug(f"Parsing inference result: backend={backend}, raw_keys={list(result.keys())}")
logger.debug(f"NMS filter: {before} predictions → {after} after confidence/IoU filtering")
```

---

## What NOT to Log

- Frame-by-frame camera reads (too high frequency — would flood the log)
- Individual pixel/mask values
- API tokens or credential values

---

## Files Touched

1. `mpcamera/controllers/camera_page.py`
2. `mpcamera/ui/results_window.py`
3. `mpcamera/ui/zoomable_view.py`
4. `mpcamera/utils/inference_utils.py`
5. `mpcamera/services/roboflow.py`
6. `mpcamera/services/directus.py`
7. `mpcamera/config.py`
8. `mpcamera/utils/local_models_utils.py`

## Success Criteria

- No bare `except Exception:` block in any of the above files is silent
- Every `print()` call replaced with the appropriate logger call
- After triggering inference, the log file shows: what model was used, what sample was selected, how many particles were found, and whether the Directus upload succeeded
- After any failure, the log file contains a full traceback
