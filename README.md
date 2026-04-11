# SoilSight GUI: Microplastic Morphometric Analysis Tool

![Project Status](https://img.shields.io/badge/Status-Thesis_Project-blue)
![Python](https://img.shields.io/badge/Python-3.11%2B-yellow)
![Framework](https://img.shields.io/badge/Framework-PyQt6-green)
![AI](https://img.shields.io/badge/Inference-Roboflow%20%2B%20PyTorch-orange)

## 📖 Overview

**SoilSight** is a desktop application that automates detection and morphometric analysis of microplastic particles from microscopy images and live camera feeds. It reduces manual annotation effort by combining instance segmentation models (PyTorch) with a PyQt6-based GUI and optional cloud integrations (Roboflow, Directus).

This repository contains the GUI, local model artifacts, inference helpers, and service connectors used for data export and remote model hosting.

## ✨ Key Features

- **Instance Segmentation:** Detects particles and displays segmentation masks and confidence scores.
- **Morphometrics:** Computes area, perimeter, equivalent circular diameter, aspect ratio, circularity, skeleton length, and other shape metrics.
- **Color Analysis:** Extracts color composition for each detected particle.
- **Live & Batch Processing:** Works with live camera feeds (microscope cameras) and static image batches.
- **Services Integration:** Supports Directus for record storage and Roboflow for remote inference/annotations via `services/` connectors.
- **Extensible UI:** Separate pages for Camera, Farm (project management), and Samples.

## Quickstart

### Prerequisites

- Python 3.11 or newer
- A GPU is recommended for local inference with PyTorch, but CPU will work for smaller images or testing.
- **Roboflow Inference Server must be installed and running** — see [Roboflow Inference Installation](https://inference.roboflow.com/install/) for detailed setup instructions.

### Installation & Setup

**Step 1: Install Roboflow Inference (required first)**

Follow the [official Roboflow Inference installation guide](https://inference.roboflow.com/install/). Then start the server on your device before running SoilSight:

```bash
# After installing inference-cli
inference server start --dev
# Server will run on http://localhost:9001
```

**Step 2: Setup and Run SoilSight**

```bash
python -m venv .venv311
source .venv311/bin/activate  # On Windows: .\.venv311\Scripts\Activate.ps1
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your Roboflow API key and workspace

python main.py
```

### macOS: "Untrusted" App Warning

If you encounter an "untrusted developer" warning when opening the packaged DMG app, run:

```bash
xattr -d com.apple.quarantine /Applications/SoilSight.app
```

Then launch the app normally.

## Roboflow Inference Setup

### Option 1: Local Inference Server (Recommended for Development)

The app defaults to using a local Roboflow Inference server on `http://localhost:9001`. This is ideal for offline work and avoids cloud API rate limits.

**⚠️ Important:** Install and start the Roboflow Inference server **before** launching SoilSight. Follow the [official Roboflow Inference installation guide](https://inference.roboflow.com/install/) for complete setup instructions.

**Quick Start: Using Python CLI**

```bash
pip install inference-cli
inference server start --dev
# Server runs at http://localhost:9001
```

**Alternative: Using Docker (all platforms)**

```bash
docker pull roboflow/roboflow-inference-server-cpu:latest
docker run -p 9001:9001 roboflow/roboflow-inference-server-cpu:latest
```

For complete installation options and troubleshooting, see [Roboflow Inference Installation](https://inference.roboflow.com/install/).

**Configure SoilSight for Local Inference:**

Set your Roboflow credentials in `.env` (created during Quickstart setup):

```bash
ROBOFLOW_API_KEY = "<YOUR_ROBOFLOW_API_KEY>"
ROBOFLOW_WORKSPACE = "soilsight-xstgr"
ROBOFLOW_WORKFLOW = "detect-count-and-visualize"
ROBOFLOW_API_URL = "http://localhost:9001"  # Local inference server
```

Then run `python main.py` once the inference server is active.

### Option 2: Roboflow Cloud/Serverless Endpoints

If you prefer cloud-hosted inference, update your `.env` file:

```bash
ROBOFLOW_API_KEY = "<YOUR_ROBOFLOW_API_KEY>"
ROBOFLOW_WORKSPACE = "<YOUR_WORKSPACE>"
ROBOFLOW_WORKFLOW = "<YOUR_WORKFLOW_ID>"
ROBOFLOW_API_URL = "https://serverless.roboflow.com"
```

Then run:

```bash
python main.py
```

⚠️ Note: Cloud inference requires internet connectivity and may have API rate limits.

Running the app will open the Qt GUI. The main entry point is `main.py` and navigation is handled by `ui_nav.py`.

## Usage / UI Overview

- `Camera` page: start/stop live capture, run real-time inference, save snapshots.
- `Farm` page: manage projects, metadata, and batch operations.
- `Samples` page: review saved images, re-run inference, export results.

UI files are located in `layouts/` and controllers are in `mpcamera/controllers/` (e.g. `camera_page.py`, `farm_page.py`, `samples_page.py`).

Prediction debugging output can be found in `prediction_debug.txt` (root and `mpcamera/`).

## Models

Local model weights are stored in the `models/` folder. Examples:

- `optimized-maskrcnn-resnet50.pth`
- `PH-optimized-maskrcnn-resnet101.pth`

To use a local model, set the appropriate model path in the app settings or update `utils/local_models_utils.py` / `utils/inference_utils.py` as needed. The app also includes support for Roboflow-hosted models via `services/roboflow.py`.

## Logging & Debugging

Logs are written to `~/.mpcamera/debug.log` and the console. For troubleshooting issues:

```bash
# View live logs (development)
tail -f ~/.mpcamera/debug.log

# View packaged app logs (after running DMG)
tail -f ~/.mpcamera/debug.log
```

All errors are logged with full tracebacks for debugging. Check the logs if:
- Inference doesn't start
- Camera doesn't initialize
- UI pages don't load
- Models fail to load

## Configuration

Application settings are stored at `~/.mpcamera/config.json`. The schema is defined in `mpcamera/config_schema.json`. Settings include:

- Model path (local or Roboflow)
- Camera device selection
- Pixel-to-micrometer scale
- API credentials (can be synced from `.env`)

To reset to defaults, delete `~/.mpcamera/config.json` and restart the app.

## Testing

Run the test suite:

```bash
python -m pytest tests/ -v
```

## Architecture (high level)

GUI (PyQt6) -> Inference layer (PyTorch models + `utils/inference_utils.py`) -> Morphometrics utilities (`utils/morphometrics/*`) -> Services (`services/directus.py`, `services/roboflow.py`) for export and remote inference.

## Code Organization

- `main.py` — application entry point
- `ui_nav.py` — navigation and startup logic
- `mpcamera/` — main package with controllers, UI helpers, and assets
  - `controllers/` — page logic (camera, farm, samples, settings)
  - `services/` — external integrations (Directus, Roboflow)
  - `utils/` — image processing, inference helpers, and morphometric calculators
  - `logging_utils.py` — centralized logging configuration
  - `path_utils.py` — file path resolution for development and bundled environments
  - `config.py` — application configuration with JSON schema validation
- `layouts/` — Qt Designer `.ui` files
- `models/` — local model weights (gitignored)
- `build/` — packaging scripts for macOS and Windows
