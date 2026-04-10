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
| `mpcamera/utils/inference_utils.py` | Normalize multi-architecture model outputs; confidence/IoU filtering |
| `mpcamera/utils/local_models_utils.py` | Load and run local `.pth`/`.pt` models; device selection |
| `mpcamera/services/roboflow.py` | Roboflow cloud/local server client (thread-safe singleton) |
| `mpcamera/services/directus.py` | REST client for Directus (sites, soilsamples, microplastics collections) |
| `mpcamera/utils/morphometrics/` | 8 shape metric modules operating in μm units |
| `mpcamera/utils/um_per_pixel.py` | Convert pixel dimensions → μm using sensor specs + magnification |
| `mpcamera/config.py` | JSON-schema-validated settings with env var override support |

### UI Files
Qt Designer `.ui` files live in `mpcamera/layouts/`. Edit them with Qt Designer; do not hand-edit XML. Controllers load them via `uic.loadUi()`.

### Local Model Weights
Stored in `models/` (gitignored). `LocalModelInference` expects `.pth` (MaskRCNN/RF-DETR) or `.pt` (YOLOv11) files placed there and selected via Settings page.
