# SoilSight GUI: Microplastic Morphometric Analysis Tool

![Project Status](https://img.shields.io/badge/Status-Thesis_Project-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)
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

Prerequisites:

- Python 3.10 or newer (project uses a `venv` by default).
- A GPU is recommended for local inference with PyTorch, but CPU will work for smaller images or testing.

Basic setup (PowerShell example):

```powershell
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Roboflow Inference (Cloud) Setup

If you want to use Roboflow-hosted workflows/models, install dependencies first, then set your Roboflow credentials before starting the app.

PowerShell example:

```powershell
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -r requirements.txt

# Required for cloud/private workflows
$env:ROBOFLOW_API_KEY = "<YOUR_ROBOFLOW_API_KEY>"
$env:ROBOFLOW_WORKSPACE = "<YOUR_WORKSPACE>"
$env:ROBOFLOW_WORKFLOW = "<YOUR_WORKFLOW_ID>"

# Set this when using Roboflow hosted/serverless inference endpoint
# (leave unset for local inference server on http://localhost:9001)
$env:ROBOFLOW_API_URL = "<YOUR_ROBOFLOW_INFERENCE_API_URL>"

python main.py
```

Quick connectivity check (optional):

```powershell
python -c "from inference_sdk import InferenceHTTPClient; import os; client = InferenceHTTPClient(api_url=os.getenv('ROBOFLOW_API_URL','http://localhost:9001'), api_key=os.getenv('ROBOFLOW_API_KEY','')); print('Roboflow client ready:', type(client).__name__)"
```

If you also want to run a local Roboflow Inference server for development, install and run:

```powershell
pip install inference-cli
inference server start --dev
```

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

## Architecture (high level)

GUI (PyQt6) -> Inference layer (PyTorch models + `utils/inference_utils.py`) -> Morphometrics utilities (`utils/morphometrics/*`) -> Services (`services/directus.py`, `services/roboflow.py`) for export and remote inference.

## Code Organization

- `main.py` — application entry point
- `ui_nav.py` — navigation and startup logic
- `mpcamera/` — package with controllers, UI helpers, and assets
- `layouts/` — Qt Designer `.ui` files
- `models/` — model weights and artifacts
- `services/` — external integrations (Directus, Roboflow)
- `utils/` — image processing, inference helpers, and morphometric calculators
