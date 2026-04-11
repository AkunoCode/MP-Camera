# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SoilSight** is a PyQt6 desktop application for microplastic morphometric analysis using microscope cameras and computer vision models. It captures live microscope frames, runs instance segmentation inference, and computes shape metrics (area, perimeter, circularity, ECD, etc.) in micrometers.

## Setup & Running

### Prerequisites
- **Python 3.11+**
- **Roboflow Inference Server running** before launching the app (see [Roboflow Inference Installation](https://inference.roboflow.com/install/))

### Step 1: Start Roboflow Inference Server (required first)

```bash
pip install inference-cli
inference server start --dev
# Server runs at http://localhost:9001
```

### Step 2: Setup SoilSight

```bash
# Create and activate virtual environment
python -m venv .venv311
source .venv311/bin/activate  # Mac/Linux
# .venv311\Scripts\Activate.ps1  # Windows PowerShell

pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your API keys and endpoints

python main.py
```

**Environment variables** (in `.env`):
- Roboflow: `ROBOFLOW_API_KEY`, `ROBOFLOW_WORKSPACE`, `ROBOFLOW_WORKFLOW`, `ROBOFLOW_API_URL`
- Directus (optional): `DIRECTUS_URL`, `DIRECTUS_TOKEN`

**User config** is stored at `~/.mpcamera/config.json` (schema in `mpcamera/config_schema.json`). Settings are cached and can be reset by deleting this file.

## Architecture

### Navigation Flow
`main.py` → `ui_nav.py (MainWindow)` → stacked widget pages (indices 0–4: Home, Farm, Samples, Camera, Settings). Each page's `.ui` file is loaded dynamically; logic lives in the corresponding controller.

### Inference Pipeline
1. `CameraWorker` (QTimer loop) captures OpenCV frames → displayed in `ZoomableView`
2. User triggers inference → `InferenceWorker` (QThread) runs one of:
   - `LocalModelInference` (auto-detects MaskRCNN/YOLOv11/RF-DETR from `.pth`/`.pt` weights)
   - `RoboflowClient` (cloud or local server via `inference-sdk`)
3. Raw outputs → `inference_utils.parse_result_to_preds()` → standardized predictions dict
4. `apply_confidence_iou_filters()` → NMS filtering
5. Per-particle morphometrics computed via `mpcamera/utils/morphometrics/` modules (all accept `S_um_per_px` for pixel-to-micrometer conversion)
6. `overlays.py` renders masks/bboxes on image; `results_window.py` shows metrics table
7. Results optionally uploaded to Directus via `DirectusClient`

### Key Design Patterns
- **Qt signals/slots** for all worker→UI communication (never update UI from threads directly)
- **Singleton** for `Settings` (config cache) and `RoboflowClient`
- **Standardized predictions dict**: all inference backends output the same format via `parse_result_to_preds()`
- `LocalModelInference` auto-detects model architecture at load time from file extension and checkpoint contents

### Module Responsibilities
| Module | Responsibility |
|---|---|
| `main.py` | App initialization, logging setup, resource path resolution |
| `ui_nav.py` | Page navigation, Directus data fetch on startup, `dataLoaded` signal |
| `mpcamera/controllers/camera_page.py` | Live capture, inference trigger, morphometric dispatch, results display |
| `mpcamera/controllers/farm_page.py` | Farm/site management UI controller |
| `mpcamera/controllers/samples_page.py` | Soil sample listing and selection UI controller |
| `mpcamera/controllers/settings_page.py` | App settings UI controller (model path, camera, scale) |
| `mpcamera/logging_utils.py` | Centralized logging setup; DEBUG to file, INFO+ to console |
| `mpcamera/path_utils.py` | Path resolution for dev and bundled (PyInstaller) environments |
| `mpcamera/config.py` | JSON-schema-validated settings with env var override support |
| `mpcamera/utils/camera_worker.py` | QTimer-based camera capture loop; emits frames to main thread |
| `mpcamera/utils/inference_worker.py` | QThread wrapper that runs inference and emits `finished` signal |
| `mpcamera/utils/inference_utils.py` | Normalize multi-architecture model outputs; confidence/IoU filtering |
| `mpcamera/utils/local_models_utils.py` | Load and run local `.pth`/`.pt` models; device selection |
| `mpcamera/utils/results_manager.py` | Aggregate and format per-particle morphometric results |
| `mpcamera/utils/prediction_utils.py` | Post-processing helpers for prediction dicts |
| `mpcamera/services/roboflow.py` | Roboflow cloud/local server client (thread-safe singleton) |
| `mpcamera/services/directus.py` | REST client for Directus (sites, soilsamples, microplastics collections) |
| `mpcamera/utils/morphometrics/` | 8 shape metric modules operating in μm units |
| `mpcamera/utils/um_per_pixel.py` | Convert pixel dimensions → μm using sensor specs + magnification |
| `mpcamera/ui/overlays.py` | Render masks/bboxes onto images |
| `mpcamera/ui/results_window.py` | Metrics table dialog shown after inference |
| `mpcamera/ui/zoomable_view.py` | Pan/zoom QGraphicsView for live and result frames |

### UI Files
Qt Designer `.ui` files live in `mpcamera/layouts/`. Edit them with Qt Designer; do not hand-edit XML. Controllers load them via `uic.loadUi()`. Always use `get_resource_path()` to locate UI files to support both dev and bundled environments.

### Local Model Weights
Stored in `models/` (gitignored). `LocalModelInference` expects `.pth` (MaskRCNN/RF-DETR) or `.pt` (YOLOv11) files placed there and selected via Settings page.

### Path Resolution (Development vs Bundled)
Use `mpcamera/path_utils.py` for all resource lookups:
```python
from mpcamera.path_utils import get_resource_path

# Works in both development and PyInstaller bundled app
ui_path = get_resource_path("mpcamera/layouts/cameraPage.ui")
icon_path = get_resource_path("mpcamera/assets/logo.png")
```

In development: returns project root relative paths
In bundled app (DMG/EXE): returns `sys._MEIPASS` relative paths (PyInstaller's temporary extraction directory)

This ensures the packaged app can find resources without modifying relative paths.

## Testing

```bash
python -m pytest tests/ -v
```

## Known Gotchas

### Thread Safety & Qt Signals

- **Frame buffer safety**: `_raw_frame_np` and `_current_frame_np` in `camera_page.py` are written by `CameraWorker` (QTimer) and read by display and inference pipelines — **always protect with a mutex/lock** when sharing.
  
  ```python
  # ❌ WRONG - race condition
  frame = self._current_frame_np  # could be halfway through update
  
  # ✅ RIGHT - use lock
  with self._frame_lock:
      frame = self._current_frame_np.copy()
  ```

- **Signal marshaling**: Qt signals from worker QThreads are safe via queued connections (default), but GUI updates must happen on main thread:
  
  ```python
  # ❌ WRONG - updates UI from worker thread
  def on_inference_done(self, results):
      self.label.setText("Done")  # crashes or undefined behavior
  
  # ✅ RIGHT - emit signal, connect to slot on main thread
  self.inference_done.connect(self.on_inference_done)  # auto-marshaled
  # or use QMetaObject.invokeMethod if not a signal/slot
  ```

- **Qt objects to worker threads**: Never pass QPixmap, QImage, QLabel, etc. to worker threads — convert to numpy or bytes on main thread first.
  
  ```python
  # ❌ WRONG
  worker.process(self.current_pixmap)  # QPixmap on worker thread = crash
  
  # ✅ RIGHT
  frame_np = cv2.cvtColor(np.array(self.current_pixmap.toImage().convertToFormat(...)), ...)
  worker.process(frame_np)  # numpy is thread-safe
  ```

- **`.ui` files**: Do not hand-edit XML in `mpcamera/layouts/`; use Qt Designer only. Hand-edits cause merge conflicts and lose Designer metadata.

- **36 identified issues** (19 high severity) catalogued in `docs/optimization-analysis.md` — consult before touching threading, NMS, or camera capture code.

## Development Rules

### Logging & Error Handling

**Setup**: Logging is centralized via `mpcamera/logging_utils.py`. It's initialized in `main.py` and writes to both console and `~/.mpcamera/debug.log`.

**Using logging in any module:**
```python
import logging
from mpcamera.logging_utils import get_logger

logger = get_logger(__name__)

# Use it
logger.info("Something happened")
logger.error("Error occurred", exc_info=True)  # exc_info=True captures full traceback
logger.debug("Detailed debugging info")
logger.warning("Warning message")
```

**Rules:**
- **All errors must be logged**, never silent `except pass` (this hides bugs)
  ```python
  # ❌ WRONG - swallows exceptions
  except Exception:
      pass
  
  # ✅ RIGHT - log with traceback
  except Exception as e:
      logger.error("Camera initialization failed", exc_info=True)
  ```
- Use `logger.error(..., exc_info=True)` to capture full tracebacks for debugging
- Log at the right level:
  - `DEBUG`: Detailed info (function entry, parameter values, low-level operations)
  - `INFO`: Important events (module initialized, data loaded, camera started)
  - `WARNING`: Something unexpected but recoverable (fallback used, missing optional config)
  - `ERROR`: Failure that impacts functionality (API unreachable, camera failed to open)
- **Never log sensitive data**: API keys, tokens, passwords, auth headers. Log only non-sensitive parts like endpoint URL:
  ```python
  # ❌ WRONG
  logger.info(f"Connecting to {url} with token {ROBOFLOW_API_KEY}")
  
  # ✅ RIGHT
  logger.info(f"Connecting to inference server at {url}")
  logger.debug(f"Using workspace: {workspace}")  # non-sensitive metadata
  ```
- **Log location**:
  - Development: `~/.mpcamera/debug.log` (DEBUG level) + console (INFO level)
  - Packaged app: same, allows debugging after installation
- All modules use `logger = get_logger(__name__)` for consistent formatting

### API Credentials
- **Never print API keys** in logs or console output. Use `logger.debug()` with only non-sensitive parts (e.g., endpoint, not token).
- API credentials are stored in `~/.mpcamera/config.json` and can be synced from `.env` via `sync_env_to_config()`.
- Environment variables only supplement config.json, never replace it entirely.

### QThread Best Practices

All background work uses one of two patterns:

**Pattern 1: QTimer Loop (Camera Capture)**
```python
class CameraWorker:
    def __init__(self, parent):
        self.timer = QTimer()
        self.timer.timeout.connect(self.capture_frame)
        self.timer.start(33)  # ~30 FPS
    
    def capture_frame(self):
        frame = self.camera.read()
        self.frame_captured.emit(frame)  # Signal to main thread
```

**Pattern 2: QThread Worker (Heavy Work)**
```python
class InferenceWorker(QThread):
    finished = pyqtSignal(dict)  # Signal results to main thread
    
    def run(self):  # Override run(), never call directly
        try:
            results = self.model.predict(...)
            self.finished.emit(results)  # Thread-safe signal
        except Exception:
            logger.error("Inference failed", exc_info=True)
            self.finished.emit({})  # Always emit something

# Main thread:
worker = InferenceWorker()
worker.finished.connect(self.on_inference_done)
worker.start()  # Runs in background, signals when done
```

Key rules:
- Override `run()`, never call `run()` directly — call `start()`
- Emit signals to communicate back to main thread (thread-safe via Qt event queue)
- Always wrap run() in try/except and log errors
- Don't hold references to worker longer than needed or use `deleteLater()`

### Directus Data Loading
- Directus data (sites, soilsamples) is fetched on app startup in a background thread by `ui_nav.py:_start_directus_fetch()`.
- The fetch emits `MainWindow.dataLoaded` signal when complete; controllers listen for this to populate UI.
- Always wrap Directus API calls in try/except and log both success and failure.
- Use `requests` Session for connection pooling and timeout control.

### Dependency Pinning & Compatibility
- **All dependencies in `requirements.txt` are pinned to specific versions** to ensure reproducible builds across local and CI/CD environments.
- PyQt6 must be **6.11.0 or later** (earlier versions lack required Qt symbols for camera/multimedia support).
- Heavy packages like torch, torchvision, ultralytics, and sklearn require their data files and hidden imports to be declared in `SoilSight.spec`.
- Do not unpin versions without testing the full build chain locally first.

### PyInstaller & Packaging
- **Always test locally first**: Run `./build/build_mac.sh` and install the `.dmg` before pushing a release tag.
  - The local build tests that all imports are available and hidden imports are correct.
  - GitHub Actions uses the same `requirements.txt` but may build on different OS/arch.
- **Debug the packaged app**: Check `~/.mpcamera/debug.log` after running the DMG/EXE to see any startup errors.
- **Common packaging issues**:
  - Missing hidden imports in `SoilSight.spec` → symbol not found errors at runtime
  - Unpinned dependencies → different package versions in CI vs local (e.g., PyQt6 6.4.2 vs 6.11.0)
  - Missing data files → `.ui` files or assets not found (use `get_resource_path()` to avoid this)
- **macOS specific**: If users get "untrusted developer" warning, they can run:
  ```bash
  xattr -d com.apple.quarantine /Applications/SoilSight.app
  ```
- Sensitive files (`.env`, `models/`) are intentionally excluded from the bundle.

## Release Process

### Before Tagging
1. **Test locally**: Run `./build/build_mac.sh` and install the generated DMG
   - Verify camera page loads and functions
   - Test inference (local or cloud)
   - Check that all dropdowns populate (farms, samples)
   - Verify no ERROR entries in `~/.mpcamera/debug.log`
2. **Verify dependencies**: Ensure all versions in `requirements.txt` are pinned and tested
3. **Check for API keys in code**: Never commit `.env` or log API keys
   ```bash
   git diff HEAD~1 | grep -i "api_key\|token\|password"  # Should be empty
   ```

### Tag and Release
1. **Create annotated tag**: `git tag -a vX.Y.Z -m "Release X.Y.Z"`
2. **Push tag**: `git push origin vX.Y.Z` (triggers GitHub Actions)
3. **Monitor CI**: Watch https://github.com/AkunoCode/MP-Camera/actions
   - Both macOS and Windows builds must succeed
   - If a build fails, check the logs in Actions for:
     - Missing hidden imports → add to `SoilSight.spec`
     - Unpinned dependency version mismatch → pin in `requirements.txt` and rebuild locally
     - Path resolution issues → ensure all resource paths use `get_resource_path()`

### Verify Release
1. **Download artifacts**: Get `SoilSight-X.Y.Z-mac.dmg` and `.exe` from the release page
2. **Test on clean system** (if possible): Install and run to verify no environment assumptions
3. **Check asset integrity**: Both DMG and EXE should be present with reasonable file sizes

### If Build Fails in CI
- Do NOT just re-run — the same code will fail again
- Reproduce locally first: `./build/build_mac.sh` 
- Fix the issue, commit, and re-tag: `git tag -f -a vX.Y.Z` + `git push origin vX.Y.Z -f`
- Common fixes:
  - Missing hidden imports in spec → rebuild locally to test
  - Unpinned deps pulling wrong version → test full build locally
  - Path issues in bundled app → run the local DMG to verify
