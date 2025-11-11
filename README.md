# Roboflow / Inference GUI (PyQt5)

A small desktop GUI that uploads images or streams webcam frames to a Roboflow-like inference workflow and displays the JSON result and any visualization returned by the workflow.

This repository was refactored into a small package. The launcher is `main.py` and the app logic lives in the `mpcamera/` package.

## Project layout

- `main.py` — small application launcher (starts the Qt event loop).
- `mpcamera/` — package containing the refactored application code:
  - `mpcamera/ui.py` — the `MainWindow` UI class (PyQt5 widgets and wiring).
  - `mpcamera/workers.py` — background threads (`Worker`, `VideoWorker`) that call the inference SDK.
  - `mpcamera/utils.py` — utility helpers (e.g. `find_base64_image`).
- `requirements.txt` — Python dependencies (install into a virtualenv).

## Quickstart (Windows PowerShell)

1. Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Provide an API key for the inference service. Two options:

- Set an environment variable for the current session (PowerShell):

```powershell
$env:ROBOFLOW_API_KEY = 'YOUR_API_KEY_HERE'
```

- Or create a `.env` file in the project root with:

```text
ROBOFLOW_API_KEY=YOUR_API_KEY_HERE
```

If `python-dotenv` is installed the app will automatically load `.env` at startup.

3. Start the GUI:

```powershell
python main.py
```

## Basic usage

- Click "Load Image" to select a local image.
- Click "Run Workflow" to send the image to the configured workflow.
- Toggle "Start Live" to stream webcam frames to the workflow (requires OpenCV or the streaming pipeline SDK).
- JSON results appear in the bottom panel. If a visualization image (data URL or base64) is found in the response, it replaces the preview and can be saved via "Save Visualization".

## Configuration notes

- `api_url` defaults to `https://serverless.roboflow.com`.
- `api_key` may be provided via the Settings dialog or via `ROBOFLOW_API_KEY` env var / `.env` file.
- `workspace_name` and `workflow_id` are now editable in the Settings dialog (open the app and click the "Settings" button).

## Dependencies and optional features

- Required for UI: `PyQt5` (installed from `requirements.txt`).
- Optional / recommended for full functionality:
  - `opencv-python` — required for webcam fallback when the streaming pipeline isn't available.
  - `numpy` — used for image conversions returned by some streaming SDKs.
  - `inference_sdk` (project-specific) — provides `InferenceHTTPClient` used to call the workflow.
  - `inference` (optional streaming pipeline) — if available, `VideoWorker` will prefer the streaming pipeline for lower latency.

If any optional package is missing the app will start but certain features will be disabled and the UI will show helpful errors.

## Troubleshooting

- If the GUI fails to start with an ImportError for `PyQt5`, install it into your virtualenv. On Windows:

```powershell
pip install PyQt5
```

- If live webcam streaming does not work, ensure OpenCV is installed and the webcam is available:

```powershell
pip install opencv-python
```

- If workflow calls fail, confirm `inference_sdk` is installed and the `api_url`/`api_key`/`workspace`/`workflow_id` are correct.

# Roboflow / Inference GUI (PyQt5)

This is a small PyQt5 GUI that uploads an image and runs a Roboflow `InferenceHTTPClient` workflow (serverless) and shows the JSON result and any visualization returned.

Files added:

- `main.py` — the PyQt5 GUI application
- `requirements.txt` — Python dependencies

Quick start

1. Create a virtual environment and activate it (Windows PowerShell example):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Provide your API key. You can either paste it into the API key field in the app, or set the environment variable `ROBOFLOW_API_KEY` before launching the app. Example (PowerShell):

```powershell
$env:ROBOFLOW_API_KEY = 'YOUR_API_KEY_HERE'
```

Alternatively, you can create a `.env` file in the project root (recommended for local dev). Copy `.env.example` to `.env` and fill in your real key:

```
ROBOFLOW_API_KEY=YOUR_API_KEY_HERE
```

The application will automatically load `.env` when `python-dotenv` is installed (it has been added to `requirements.txt`).

3. Run the GUI:

```powershell
python main.py
```

How it works

- Click "Load Image" and pick a local image file.
- Click "Run Workflow" to send the image to the configured workflow.
- The app runs the inference in a background thread and shows the pretty-printed JSON in the lower panel.
- If a visualization image (data URL or base64) is found in the response, it will replace the preview and you can save it using "Save Visualization".

Configuration

- `api_url` defaults to `https://serverless.roboflow.com`.
- `api_key` can be provided via the UI or `ROBOFLOW_API_KEY` env var.
- `workspace_name` and `workflow_id` fields are pre-filled with the example values from your snippet; edit them if you need to target a different workflow.

Notes and caveats

- This project expects a Python package named `inference_sdk` which exposes `InferenceHTTPClient` (as in your snippet). Make sure that package is installed and available in your environment.
- The app includes some heuristics to find base64-encoded visualization images in the response; if your workflow returns images under a specific key, the app should find it, but you can adapt the `find_base64_image` function to the exact response shape.
