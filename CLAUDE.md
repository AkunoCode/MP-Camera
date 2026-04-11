# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SoilSight** is a PyQt6 desktop application for microplastic morphometric analysis using microscope cameras and computer vision models. It captures live microscope frames, runs instance segmentation inference, and computes shape metrics (area, perimeter, circularity, ECD, etc.) in micrometers.

## Setup & Running

```bash
# Create and activate virtual environment
python -m venv .venv311
source .venv311/bin/activate  # Mac/Linux
# .venv311\Scripts\Activate.ps1  # Windows PowerShell

pip install -r requirements.txt

# Run the app
python main.py
```

**Environment variables** (copy `.env.example` to `.env`):
- `ROBOFLOW_API_KEY`, `ROBOFLOW_WORKSPACE`, `ROBOFLOW_WORKFLOW`, `ROBOFLOW_API_URL`
- Directus: `DIRECTUS_URL`, `DIRECTUS_TOKEN`

**Optional local Roboflow inference server:**
```bash
pip install inference-cli
inference server start --dev
# Server runs at http://localhost:9001
```

**User config** is stored at `~/.mpcamera/config.json` (schema in `mpcamera/config_schema.json`).

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
| `ui_nav.py` | Page navigation, Directus data fetch on startup, `dataLoaded` signal |
| `mpcamera/controllers/camera_page.py` | Live capture, inference trigger, morphometric dispatch, results display |
| `mpcamera/controllers/farm_page.py` | Farm/site management UI controller |
| `mpcamera/controllers/samples_page.py` | Soil sample listing and selection UI controller |
| `mpcamera/controllers/settings_page.py` | App settings UI controller (model path, camera, scale) |
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
| `mpcamera/config.py` | JSON-schema-validated settings with env var override support |
| `mpcamera/ui/overlays.py` | Render masks/bboxes onto images |
| `mpcamera/ui/results_window.py` | Metrics table dialog shown after inference |
| `mpcamera/ui/zoomable_view.py` | Pan/zoom QGraphicsView for live and result frames |

### UI Files
Qt Designer `.ui` files live in `mpcamera/layouts/`. Edit them with Qt Designer; do not hand-edit XML. Controllers load them via `uic.loadUi()`.

### Local Model Weights
Stored in `models/` (gitignored). `LocalModelInference` expects `.pth` (MaskRCNN/RF-DETR) or `.pt` (YOLOv11) files placed there and selected via Settings page.

## Testing

```bash
python -m pytest tests/ -v
```

## Known Gotchas

- **Thread safety on frames**: `_raw_frame_np` and `_current_frame_np` in `camera_page.py` are written by the camera worker and read by both the display pipeline and inference worker — always protect with a mutex. See `docs/optimization-analysis.md` issue 7.1.
- **Signal marshaling**: Qt signals emitted from worker QThreads are normally safe via queued connections, but don't emit GUI-touching signals directly from threads; use `QMetaObject.invokeMethod` with `Qt.QueuedConnection` when in doubt. See issue 7.2.
- **Never hand Qt GUI objects (QPixmap, QImage) to worker threads** — convert to numpy/bytes on the main thread first.
- **`.ui` files**: Do not hand-edit XML in `mpcamera/layouts/`; use Qt Designer only.
- **36 identified issues** (19 high severity) catalogued in `docs/optimization-analysis.md` — consult before touching threading, NMS, or camera capture code.

## Development Rules

### Logging & Error Handling
- **All errors must be logged**, never silent `except pass`. Use `logger.error()` with `exc_info=True` for full tracebacks.
- Packaged app debug logs go to `~/.mpcamera/debug.log` (set up in `main.py`).
- Use `import logging; logger = logging.getLogger(__name__)` in all modules that need error tracking.

### API Credentials
- **Never print API keys** in logs or console output. Use `logger.debug()` with only non-sensitive parts (e.g., endpoint, not token).
- API credentials are stored in `~/.mpcamera/config.json` and can be synced from `.env` via `sync_env_to_config()`.
- Environment variables only supplement config.json, never replace it entirely.

### Directus Data Loading
- Directus data (sites, soilsamples) is fetched on app startup in a background thread by `ui_nav.py:_start_directus_fetch()`.
- The fetch emits `MainWindow.dataLoaded` signal when complete; controllers listen for this to populate UI.
- Always wrap Directus API calls in try/except and log both success and failure.

### PyInstaller & Packaging
- **Always test locally**: Run `./build/build_mac.sh` and install the `.dmg` before pushing a release tag.
- Debug the packaged app by checking `~/.mpcamera/debug.log` after running it.
- If packaging fails, check `SoilSight.spec` for missing hidden imports or data files.
- Sensitive files (`.env`, `models/`) are intentionally excluded from the bundle.

## Release Process

1. **Local test**: Run `./build/build_mac.sh` and test the generated DMG
2. **Check logs**: Verify `~/.mpcamera/debug.log` shows no ERROR level entries
3. **Tag and push**: `git tag vX.Y.Z && git push origin vX.Y.Z`
4. **Monitor CI**: Watch https://github.com/AkunoCode/MP-Camera/actions for build completion
5. **Verify assets**: Confirm release has both `SoilSight-X.Y.Z-mac.dmg` and `SoilSight-X.Y.Z-windows-setup.exe`
