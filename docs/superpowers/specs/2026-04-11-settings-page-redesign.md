# Settings Page Redesign — Spec

**Date:** 2026-04-11  
**Status:** Approved

## Goal

Replace the current two-panel scroll layout with a horizontal tab-based layout, expose all `.env`-equivalent fields through the UI, and improve overall visual organization for non-technical users.

## Layout

Replace the existing `QScrollArea` + right panel structure with a `QTabWidget` containing 7 tabs. The right panel (title label + notes `QTextEdit`) is removed. The Save button moves inside each tab.

**Tabs (in order):**

1. Camera
2. Streaming
3. Measurement
4. Inference
5. Display
6. Models
7. Services

Each tab contains a `QGridLayout` (label column + input column) with a Save button aligned to the bottom-right.

## Services Tab (New Fields)

The Services tab is split into two labeled sub-groups with a horizontal divider between them.

### Roboflow

| Label | Widget name | Type | Config path |
|---|---|---|---|
| API Key | `roboflowApiKeyLine` | `QLineEdit` (Password + Show/Hide toggle) | `services.roboflow.api_key` |
| API URL | `roboflowApiUrlLine` | `QLineEdit` | `services.roboflow.api_url` |
| Workspace | `roboflowWorkspaceLine` | `QLineEdit` | `services.roboflow.workspace` |
| Workflow | `roboflowWorkflowLine` | `QLineEdit` | `services.roboflow.workflow` |

### Directus

| Label | Widget name | Type | Config path |
|---|---|---|---|
| API URL | `directusApiUrlLine` | `QLineEdit` | `services.directus.api_url` |
| Bearer Token | `directusBearerLine` | `QLineEdit` (Password + Show/Hide toggle) | `services.directus.bearer_token` |
| Timeout (s) | `directusTimeoutSpin` | `QSpinBox` (min 1, max 300) | `services.directus.timeout_seconds` |

## Show/Hide Toggle for Sensitive Fields

`roboflowApiKeyLine` and `directusBearerLine` each get a companion `QPushButton` ("Show") placed inline. Clicking toggles `echoMode` between `Password` and `Normal` and updates button text to "Hide"/"Show". This is wired in the controller, not the `.ui` file.

## Existing Tabs (No Field Changes)

All existing widget names are preserved exactly. Only the containing structure changes from `QScrollArea` sections to tab pages:

- **Camera:** `cameraResWidthSpin`, `cameraResHeightSpin`, `fourccLineEdit`, `forceDirectShowCheck`
- **Streaming:** `frameIntervalSpin`, `inferenceIntervalSpin`
- **Measurement:** `sensorWidthSpin`, `sensorHeightSpin`, `defaultMagnificationSpin`
- **Inference:** `defaultConfidenceSpin`, `defaultIouSpin`
- **Display:** `brightnessDefaultSpin`, `contrastDefaultSpin`
- **Models:** `localModelsDirLine`, `preferLocalCheck`

## Controller Changes (`settings_page.py`)

### `load_values()`
Add loading for 4 new fields:
- `cfg.services.roboflow.api_url` → `roboflowApiUrlLine`
- `cfg.services.roboflow.workspace` → `roboflowWorkspaceLine`
- `cfg.services.roboflow.workflow` → `roboflowWorkflowLine`
- `cfg.services.directus.api_url` → `directusApiUrlLine`
- `cfg.services.directus.timeout_seconds` → `directusTimeoutSpin`

### `_on_save_clicked()`
Add saving for the same 5 new fields into `cfg["services"]["roboflow"]` and `cfg["services"]["directus"]`.

### `_wire()`
- Wire Show/Hide toggle buttons for `roboflowApiKeyLine` and `directusBearerLine`
- The Save button (`saveSettingsButton`) remains a single button; it saves all tabs at once regardless of which tab is active

## Data Store

All values read from and written to `~/.mpcamera/config.json` via the existing `Settings` singleton. The `.env` file is not read or written by the settings page. Schema defaults from `config_schema.json` are preserved as-is.

## What Is NOT Changing

- Widget names for all existing fields (no renames)
- Config schema (`config_schema.json`) — no changes needed, all fields already exist
- `Settings.load()` / `Settings.save()` logic
- Save is still a single button saving all settings at once
