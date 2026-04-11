# Laboratory UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Camera page and Results window to look and feel like a laboratory instrument — instrument-panel chrome, data-dense readouts, tabbed image panel — while keeping the existing white/black/blue color scheme.

**Architecture:** QSS styles are centralised in a new `mpcamera/ui/styles.py` module and applied programmatically in each controller, keeping .ui files structurally minimal. The camera page `.ui` is restructured to a 3-column instrument layout and the results window `.ui` gains a `QTabWidget` for the tabbed image panel and a stats sidebar widget. Controller wiring for the new widgets (Last Run panel, tab switching, stats sidebar) is added in `camera_page.py` and `results_window.py`.

**Tech Stack:** PyQt6, Qt Designer `.ui` files, QSS stylesheets, `pytest` with `pytest-qt`

> **Note on `.ui` edits:** CLAUDE.md says to use Qt Designer rather than hand-editing XML. For this redesign the tasks that modify `.ui` files include the exact XML diffs needed; apply them with Qt Designer or carefully by editing the XML. Do not edit `.ui` XML for pages not listed here.

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| **Create** | `mpcamera/ui/styles.py` | Shared QSS constants for instrument-panel chrome and class badges |
| **Modify** | `mpcamera/layouts/cameraPage.ui` | 3-column body layout; header bar with status badge; instrument panel sections |
| **Modify** | `mpcamera/controllers/camera_page.py` | Apply new QSS; wire header breadcrumb; populate Last Run panel after inference |
| **Modify** | `mpcamera/layouts/resultsWindow.ui` | Header bar; replace `QSplitter` with `QTabWidget`+stats sidebar layout |
| **Modify** | `mpcamera/ui/results_window.py` | Apply new QSS; switch to particle tab on row selection; populate stats sidebar |
| **Create** | `tests/__init__.py` | Empty (makes tests a package) |
| **Create** | `tests/test_last_run_panel.py` | Tests: Last Run panel updates correctly after inference |
| **Create** | `tests/test_results_tab_switch.py` | Tests: row selection switches to particle tab |

---

## Task 1: Shared QSS Style Module

**Files:**
- Create: `mpcamera/ui/styles.py`

- [ ] **Step 1: Create `mpcamera/ui/styles.py`** with the shared instrument-panel QSS constants:

```python
# mpcamera/ui/styles.py
"""Shared QSS stylesheet constants for the laboratory instrument UI theme."""

# Applied to section header strips (QFrame/QLabel used as section chrome)
SECTION_HEADER_QSS = """
    background-color: #f8f9fa;
    border-bottom: 1px solid #e5e7eb;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #6b7280;
"""

# Applied to digital readout labels (conf, IoU, metric values)
READOUT_QSS = """
    font-size: 18px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: #111111;
    padding: 4px 8px;
"""

# Applied to the highlighted metric (e.g. ECD avg) — blue
READOUT_HIGHLIGHT_QSS = """
    font-size: 18px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: #2563eb;
    padding: 4px 8px;
"""

# Page header separator bar
PAGE_HEADER_QSS = """
    border-bottom: 2px solid #111111;
    padding-bottom: 8px;
    margin-bottom: 0px;
"""

# Instrument card container (bordered section)
INSTRUMENT_CARD_QSS = """
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    background-color: #ffffff;
"""

# Table column headers — applied via QHeaderView
TABLE_HEADER_QSS = """
QHeaderView::section {
    background-color: #f8f9fa;
    border: none;
    border-bottom: 2px solid #e5e7eb;
    border-right: 1px solid #e5e7eb;
    padding: 4px 6px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #6b7280;
}
"""

# Selected table row highlight
TABLE_ROW_SELECTED_QSS = "background-color: #eff6ff;"

# Class badge colors: maps lowercase class name → (background, text) hex
CLASS_BADGE_COLORS: dict[str, tuple[str, str]] = {
    "fragment": ("#dbeafe", "#1d4ed8"),
    "fiber":    ("#ede9fe", "#6d28d9"),
    "film":     ("#d1fae5", "#065f46"),
    "foam":     ("#fef9c3", "#854d0e"),
    "pellet":   ("#fee2e2", "#991b1b"),
    "sheet":    ("#f3e8ff", "#6b21a8"),
    "bead":     ("#fce7f3", "#9d174d"),
}

# Live status badge colors
STATUS_LIVE_QSS = """
    background-color: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 4px;
    color: #15803d;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
"""

STATUS_IDLE_QSS = """
    background-color: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    color: #6b7280;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
"""
```

- [ ] **Step 2: Verify import works**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -c "from mpcamera.ui.styles import CLASS_BADGE_COLORS; print('OK', list(CLASS_BADGE_COLORS.keys()))"
```

Expected: `OK ['fragment', 'fiber', 'film', 'foam', 'pellet', 'sheet', 'bead']`

- [ ] **Step 3: Commit**

```bash
git add mpcamera/ui/styles.py
git commit -m "feat: add shared QSS style constants for laboratory UI theme"
```

---

## Task 2: Camera Page `.ui` — Header Bar

**Files:**
- Modify: `mpcamera/layouts/cameraPage.ui`

The current camera page has a plain `QLabel` title at the top of `verticalLayout_5`. Replace the top section with a header bar containing:
- A two-row title (small uppercase label + bold title)
- A status badge label (`liveStatusLabel`)
- A breadcrumb label (`headerBreadcrumb`)

- [ ] **Step 1: Open `mpcamera/layouts/cameraPage.ui` in Qt Designer**

In Qt Designer, locate the `cameraSection` widget → `verticalLayout_5`. The first item is a `QLabel` named `label` with text `"Microplastic Detection Camera"`.

Replace that single `QLabel` with a `QWidget` (name it `headerBar`) containing a `QHBoxLayout` with:

**Left side** (`QVBoxLayout`):
- `QLabel` named `pageSubtitle`, text `"SoilSight · Camera"`, styleSheet: `color: #9ca3af; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;`
- `QLabel` named `pageTitle`, text `"Microplastic Detection"`, styleSheet: `font-size: 20px; font-weight: 800; color: #111111;`

**Right side** (`QHBoxLayout`, alignment right):
- `QLabel` named `headerBreadcrumb`, text `"— / —"`, styleSheet: `background-color: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 4px; padding: 2px 8px; font-size: 11px; color: #374151;`
- `QLabel` named `liveStatusLabel`, text `"● IDLE"`, styleSheet: `background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 4px; color: #6b7280; font-size: 10px; font-weight: 600; padding: 2px 8px;`

Set `headerBar` styleSheet to: `border-bottom: 2px solid #111111; padding-bottom: 8px;`

Save the `.ui` file.

- [ ] **Step 2: Verify the app still launches without errors**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -c "
from PyQt6 import QtWidgets, uic
import sys
app = QtWidgets.QApplication(sys.argv)
w = QtWidgets.QWidget()
uic.loadUi('mpcamera/layouts/cameraPage.ui', w)
assert w.findChild(QtWidgets.QLabel, 'liveStatusLabel') is not None, 'liveStatusLabel missing'
assert w.findChild(QtWidgets.QLabel, 'headerBreadcrumb') is not None, 'headerBreadcrumb missing'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add mpcamera/layouts/cameraPage.ui
git commit -m "feat(ui): add instrument-panel header bar to camera page"
```

---

## Task 3: Camera Page `.ui` — Instrument Panel Column

**Files:**
- Modify: `mpcamera/layouts/cameraPage.ui`

The current body layout has the camera view flanked by vertical sliders. Add a right-side instrument panel column.

- [ ] **Step 1: Add instrument panel widget in Qt Designer**

In the camera page body `QHBoxLayout` (named `horizontalLayout_11`), add a new `QWidget` (name: `instrumentPanel`, minimumWidth: 140px) to the right of the brightness slider. Inside `instrumentPanel`, create a `QVBoxLayout` (name: `instrumentLayout`, spacing: 6, margins: 8/8/8/8).

Add four stacked sections inside `instrumentLayout`:

**Section 1 — Model**
- `QFrame` named `modelCard`, styleSheet: `border: 1px solid #e5e7eb; border-radius: 4px;`
- Inside: `QVBoxLayout` with spacing 0
  - `QLabel` named `modelCardHeader`, text: `"MODEL"`, styleSheet: `background-color: #f8f9fa; border-bottom: 1px solid #e5e7eb; padding: 3px 8px; font-size: 10px; font-weight: 600; letter-spacing: 1px; color: #6b7280;`
  - The existing `sourceCombo` moved here (or a reference; see controller task)

**Section 2 — Thresholds**
- `QFrame` named `thresholdsCard`, styleSheet: `border: 1px solid #e5e7eb; border-radius: 4px;`
- Inside: `QVBoxLayout` with spacing 0
  - `QLabel` named `thresholdsCardHeader`, text: `"THRESHOLDS"`, same header styleSheet as above
  - `QWidget` named `thresholdsGrid` with `QGridLayout` (spacing 0):
    - Row 0 col 0: `QLabel` named `lblConfHeader`, text `"CONF"`, styleSheet: `font-size: 9px; color: #9ca3af; text-transform: uppercase; padding: 2px 8px 0 8px;`
    - Row 0 col 1: `QLabel` named `lblIouHeader`, text `"IoU"`, same styleSheet
    - Row 1 col 0: `QLabel` named `confReadout`, text `"0.72"`, styleSheet: `font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; color: #111; padding: 2px 8px 6px 8px;`
    - Row 1 col 1: `QLabel` named `iouReadout`, text `"0.55"`, same styleSheet as confReadout

**Section 3 — Run Inference button**
- Keep the existing `captureButton` (or create a new `runInferenceButton`) here — see note below
- styleSheet: `background-color: #111111; color: #ffffff; border-radius: 4px; font-weight: 700; font-size: 11px; padding: 8px; letter-spacing: 0.5px;`
- text: `"▶  RUN INFERENCE"`

> **Note:** The existing camera page has `captureButton` for "Capture Frame" and the inference is triggered elsewhere. Keep existing button wiring intact. Add a new `QPushButton` named `runInferenceButton` in this section. The controller will wire it in Task 4. The existing capture/clear buttons remain in the camera section below the feed.

**Section 4 — Last Run**
- `QFrame` named `lastRunCard`, styleSheet: `border: 1px solid #e5e7eb; border-radius: 4px;`
- Inside: `QVBoxLayout` with spacing 0
  - `QLabel` named `lastRunCardHeader`, text `"LAST RUN"`, same header styleSheet
  - `QWidget` named `lastRunContent` with `QVBoxLayout` (margins 8/6/8/6, spacing 4):
    - Row for particles: `QHBoxLayout` with `QLabel` (`"Particles"`, styleSheet: `font-size: 10px; color: #6b7280;`) + `QLabel` named `lastRunParticles`, text `"—"`, styleSheet: `font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums;`
    - Row for avg area: `QHBoxLayout` with `QLabel` (`"Avg Area"`, same label style) + `QLabel` named `lastRunAvgArea`, text `"—"`, styleSheet: `font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; color: #2563eb;`
    - Row for avg conf: `QHBoxLayout` with `QLabel` (`"Avg Conf"`, same label style) + `QLabel` named `lastRunAvgConf`, text `"—"`, styleSheet: `font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums;`

Add a vertical `QSpacerItem` at the bottom of `instrumentLayout` to push sections to the top.

Save the `.ui` file.

- [ ] **Step 2: Verify new widgets are present**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -c "
from PyQt6 import QtWidgets, uic
import sys
app = QtWidgets.QApplication(sys.argv)
w = QtWidgets.QWidget()
uic.loadUi('mpcamera/layouts/cameraPage.ui', w)
for name in ['modelCard','thresholdsCard','confReadout','iouReadout','runInferenceButton','lastRunCard','lastRunParticles','lastRunAvgArea','lastRunAvgConf']:
    assert w.findChild(QtWidgets.QWidget, name) is not None, f'{name} missing'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add mpcamera/layouts/cameraPage.ui
git commit -m "feat(ui): add instrument panel column to camera page"
```

---

## Task 4: Camera Page Controller — Wire New Widgets + Last Run Panel

**Files:**
- Modify: `mpcamera/controllers/camera_page.py`
- Create: `tests/__init__.py`
- Create: `tests/test_last_run_panel.py`

- [ ] **Step 1: Create `tests/__init__.py`** (empty file)

```bash
touch /Users/kodecraft-carlo-rabe/Desktop/MP-Camera/tests/__init__.py
```

- [ ] **Step 2: Write failing test** for Last Run panel population in `tests/test_last_run_panel.py`:

```python
# tests/test_last_run_panel.py
"""Tests for Last Run instrument panel population in CameraPageController."""
import pytest
from unittest.mock import MagicMock, patch
from PyQt6 import QtWidgets


def _make_preds(n=3, score=0.85, area=1200.0):
    """Build a minimal list of prediction dicts."""
    return [
        {
            "label": "Fragment",
            "score": score,
            "points": [[10, 10], [20, 10], [20, 20], [10, 20]],
            "bbox": [10, 10, 10, 10],
        }
        for _ in range(n)
    ]


@pytest.fixture
def app(qtbot):
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_last_run_panel_updates_particle_count(app, qtbot):
    """After _update_last_run_panel(preds), lastRunParticles shows the count."""
    from mpcamera.controllers.camera_page import CameraPageController

    page = QtWidgets.QWidget()
    # Add the required labels that the controller looks for
    particles_lbl = QtWidgets.QLabel("—", page)
    particles_lbl.setObjectName("lastRunParticles")
    area_lbl = QtWidgets.QLabel("—", page)
    area_lbl.setObjectName("lastRunAvgArea")
    conf_lbl = QtWidgets.QLabel("—", page)
    conf_lbl.setObjectName("lastRunAvgConf")

    # Patch heavy dependencies so the controller initialises without hardware
    with patch("mpcamera.controllers.camera_page.CameraWorker"), \
         patch("mpcamera.controllers.camera_page.InferenceWorker"), \
         patch.object(CameraPageController, "_populate_data"), \
         patch.object(CameraPageController, "_replace_graphics_view"), \
         patch.object(CameraPageController, "_setup_connections"):
        ctrl = CameraPageController.__new__(CameraPageController)
        ctrl.page = page
        ctrl.ui = {
            "last_run_particles": particles_lbl,
            "last_run_avg_area": area_lbl,
            "last_run_avg_conf": conf_lbl,
        }

    preds = _make_preds(n=5, score=0.90)
    ctrl._update_last_run_panel(preds)

    assert particles_lbl.text() == "5"


def test_last_run_panel_shows_dashes_when_empty(app, qtbot):
    """_update_last_run_panel([]) resets labels to '—'."""
    from mpcamera.controllers.camera_page import CameraPageController

    page = QtWidgets.QWidget()
    particles_lbl = QtWidgets.QLabel("5", page)
    particles_lbl.setObjectName("lastRunParticles")
    area_lbl = QtWidgets.QLabel("42.3", page)
    area_lbl.setObjectName("lastRunAvgArea")
    conf_lbl = QtWidgets.QLabel("0.90", page)
    conf_lbl.setObjectName("lastRunAvgConf")

    with patch("mpcamera.controllers.camera_page.CameraWorker"), \
         patch("mpcamera.controllers.camera_page.InferenceWorker"), \
         patch.object(CameraPageController, "_populate_data"), \
         patch.object(CameraPageController, "_replace_graphics_view"), \
         patch.object(CameraPageController, "_setup_connections"):
        ctrl = CameraPageController.__new__(CameraPageController)
        ctrl.page = page
        ctrl.ui = {
            "last_run_particles": particles_lbl,
            "last_run_avg_area": area_lbl,
            "last_run_avg_conf": conf_lbl,
        }

    ctrl._update_last_run_panel([])

    assert particles_lbl.text() == "—"
    assert area_lbl.text() == "—"
    assert conf_lbl.text() == "—"
```

- [ ] **Step 3: Run test — verify it fails**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -m pytest tests/test_last_run_panel.py -v
```

Expected: FAIL — `AttributeError: '_update_last_run_panel'`

- [ ] **Step 4: Add new widget lookups to `_find_ui_elements` in `camera_page.py`**

In `_find_ui_elements`, add the following entries to the `elements` dict (around line 394, after `lbl_bead`):

```python
            # Instrument panel — header
            "live_status_label": self.page.findChild(QtWidgets.QLabel, "liveStatusLabel"),
            "header_breadcrumb": self.page.findChild(QtWidgets.QLabel, "headerBreadcrumb"),
            # Instrument panel — thresholds readouts
            "conf_readout": self.page.findChild(QtWidgets.QLabel, "confReadout"),
            "iou_readout": self.page.findChild(QtWidgets.QLabel, "iouReadout"),
            # Instrument panel — run button
            "run_inference_btn": self.page.findChild(QtWidgets.QPushButton, "runInferenceButton"),
            # Instrument panel — last run
            "last_run_particles": self.page.findChild(QtWidgets.QLabel, "lastRunParticles"),
            "last_run_avg_area": self.page.findChild(QtWidgets.QLabel, "lastRunAvgArea"),
            "last_run_avg_conf": self.page.findChild(QtWidgets.QLabel, "lastRunAvgConf"),
```

- [ ] **Step 5: Add `_update_last_run_panel` method to `CameraPageController`**

Add this method after `_on_inference_worker_finished` (around line 1570):

```python
    def _update_last_run_panel(self, preds: list) -> None:
        """Populate the Last Run instrument panel with aggregate metrics from preds."""
        particles_lbl = self.ui.get("last_run_particles")
        area_lbl = self.ui.get("last_run_avg_area")
        conf_lbl = self.ui.get("last_run_avg_conf")

        if not preds:
            for lbl in (particles_lbl, area_lbl, conf_lbl):
                if lbl is not None:
                    lbl.setText("—")
            return

        count = len(preds)
        avg_conf = sum(p.get("score", 0) for p in preds) / count

        # Area requires morphometric calculation; use the existing compute_aggregates
        # helper which operates on the filtered preds list
        try:
            from mpcamera.utils.inference_utils import compute_aggregates
            aggs = compute_aggregates(preds)
            avg_area = aggs.get("avg_area", 0.0)
        except Exception:
            avg_area = 0.0

        if particles_lbl is not None:
            particles_lbl.setText(str(count))
        if area_lbl is not None:
            area_lbl.setText(f"{avg_area:.1f} μm²")
        if conf_lbl is not None:
            conf_lbl.setText(f"{avg_conf:.2f}")
```

- [ ] **Step 6: Call `_update_last_run_panel` inside `_on_inference_worker_finished`**

In `_on_inference_worker_finished`, after line 1564 (`self._update_stats(preds)`), add:

```python
            # Update Last Run instrument panel
            try:
                self._update_last_run_panel(preds)
            except Exception as e:
                print(f"[LAST RUN] Panel update failed: {e}")
```

- [ ] **Step 7: Add `_update_status_badge` method and call it from `_set_state`**

Add this method near `_set_state`:

```python
    def _update_status_badge(self) -> None:
        """Sync the live status badge label with the current camera state."""
        from mpcamera.ui.styles import STATUS_LIVE_QSS, STATUS_IDLE_QSS
        lbl = self.ui.get("live_status_label")
        if lbl is None:
            return
        if self._camera_state == CameraState.STREAMING:
            lbl.setText("● LIVE")
            lbl.setStyleSheet(STATUS_LIVE_QSS)
        elif self._camera_state == CameraState.INFERRING:
            lbl.setText("● INFERRING")
            lbl.setStyleSheet(STATUS_LIVE_QSS)
        else:
            lbl.setText("● IDLE")
            lbl.setStyleSheet(STATUS_IDLE_QSS)
```

At the end of `_set_state`, add:

```python
        try:
            self._update_status_badge()
        except Exception:
            pass
```

- [ ] **Step 8: Add `_update_header_breadcrumb` and connect it to farm/soil combo changes**

Add method:

```python
    def _update_header_breadcrumb(self) -> None:
        """Update the header breadcrumb label with the selected farm and sample."""
        lbl = self.ui.get("header_breadcrumb")
        if lbl is None:
            return
        farm_combo = self.ui.get("farm_combo")
        soil_combo = self.ui.get("soil_combo")
        farm = farm_combo.currentText() if farm_combo else "—"
        sample = soil_combo.currentText() if soil_combo else "—"
        lbl.setText(f"{farm}  /  {sample}")
```

In `_setup_connections`, add (after the existing combo connections, if any):

```python
        try:
            if self.ui.get("farm_combo"):
                self.ui["farm_combo"].currentTextChanged.connect(
                    lambda _: self._update_header_breadcrumb()
                )
            if self.ui.get("soil_combo"):
                self.ui["soil_combo"].currentTextChanged.connect(
                    lambda _: self._update_header_breadcrumb()
                )
        except Exception:
            pass
```

- [ ] **Step 9: Wire `runInferenceButton` in `_setup_connections`**

First, find the slot connected to `captureButton` (`cap_btn`) in `_setup_connections`:

```bash
grep -n "cap_btn\|captureButton\|capture" mpcamera/controllers/camera_page.py | grep "connect"
```

Note the method name (e.g. `_on_capture_clicked` or `_on_run_inference`). Then in `_setup_connections`, add next to the existing `cap_btn` connection:

```python
        try:
            if self.ui.get("run_inference_btn"):
                self.ui["run_inference_btn"].clicked.connect(
                    # Use the same slot as captureButton — found via grep above
                    self._on_capture_clicked  # replace with actual method name
                )
        except Exception:
            pass
```

- [ ] **Step 10: Apply shared QSS to the camera page**

In `_init_ui_defaults`, apply the table header QSS if an inference table exists:

```python
        from mpcamera.ui.styles import TABLE_HEADER_QSS
        try:
            inf_table = self.ui.get("inf_table")
            if inf_table is not None:
                inf_table.horizontalHeader().setStyleSheet(TABLE_HEADER_QSS)
        except Exception:
            pass
```

- [ ] **Step 11: Run tests — verify they pass**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -m pytest tests/test_last_run_panel.py -v
```

Expected:
```
PASSED tests/test_last_run_panel.py::test_last_run_panel_updates_particle_count
PASSED tests/test_last_run_panel.py::test_last_run_panel_shows_dashes_when_empty
```

- [ ] **Step 12: Commit**

```bash
git add mpcamera/controllers/camera_page.py tests/__init__.py tests/test_last_run_panel.py
git commit -m "feat: wire Last Run panel, status badge, and breadcrumb in camera page controller"
```

---

## Task 5: Results Window `.ui` — Header + Tabbed Image Panel + Stats Sidebar

**Files:**
- Modify: `mpcamera/layouts/resultsWindow.ui`

The current layout is: `QSplitter` (horizontal) → `groupImage` (QGraphicsView) | `groupData` (QTableWidget). Replace with:
- Header bar (same pattern as camera page)
- Top section: `QTabWidget` (image tabs) + stats sidebar
- Full-width table below

- [ ] **Step 1: Add header bar in Qt Designer**

Open `resultsWindow.ui`. The root layout is `verticalLayout_main` inside `centralwidget`.

**Before the existing `QSplitter`**, insert a `QWidget` named `resultsHeaderBar` with `QHBoxLayout`:

Left `QVBoxLayout`:
- `QLabel` named `resultsPageSubtitle`, text `"SoilSight · Results"`, styleSheet: `color: #9ca3af; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;`
- `QLabel` named `resultsPageTitle`, text `"Morphological Characteristics"`, styleSheet: `font-size: 20px; font-weight: 800; color: #111111;`

Right `QHBoxLayout` (aligned right):
- `QLabel` named `resultsBreadcrumb`, text `"— / —"`, styleSheet: `background-color: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 4px; padding: 2px 8px; font-size: 11px; color: #374151;`

Set `resultsHeaderBar` styleSheet: `border-bottom: 2px solid #111111; padding-bottom: 8px;`

- [ ] **Step 2: Replace QSplitter with tabbed image + stats layout**

Remove the existing `QSplitter` (which contains `groupImage` and `groupData`). Replace it with:

**Top section** — `QWidget` named `topSection`, `QHBoxLayout` (spacing 8):

Left: `QTabWidget` named `imageTabWidget`, minimumHeight 280px:
- Tab 0: `QWidget` named `tabFullImage` with tab title `"Full Image"`
  - `QVBoxLayout` with `QGraphicsView` named `fullImageView` (fill tab, ScrollHandDrag mode set in Python)
- Tab 1: `QWidget` named `tabParticle` with tab title `"Particle —"`
  - `QVBoxLayout` with `QGraphicsView` named `previewView` (this is the **existing** `previewView` moved here; keep same object name so controller code still finds it)
  - `QLabel` named `label_instructions`, text `"Scroll to zoom · Drag to pan"`, styleSheet: `color: gray; font-size: 10px;`, alignment `AlignCenter`

Right: `QWidget` named `statsSidebar`, fixedWidth 180px, `QVBoxLayout` (spacing 6, margins 0):

**Stats card — DISTRIBUTION**:
- `QFrame` named `distCard`, styleSheet `border: 1px solid #e5e7eb; border-radius: 4px;`
- Inside `QVBoxLayout` spacing 0:
  - `QLabel` named `distCardHeader`, text `"DISTRIBUTION"`, styleSheet: `background-color: #f8f9fa; border-bottom: 1px solid #e5e7eb; padding: 3px 8px; font-size: 10px; font-weight: 600; letter-spacing: 1px; color: #6b7280;`
  - `QWidget` named `distContent`, `QVBoxLayout` (margins 6/4/6/6, spacing 2):
    - For each class: a `QHBoxLayout` with a `QLabel` for the class name + `QLabel` for count. Name them:
      - `distFragmentCount` (text `"—"`), `distFiberCount`, `distFilmCount`, `distFoamCount`, `distPelletCount`, `distSheetCount`, `distBeadCount`
    - All count labels styleSheet: `font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums;`
    - All class name labels styleSheet: `font-size: 10px; color: #6b7280;`

**Stats card — AGGREGATES** (2-cell grid):
- `QFrame` named `aggsCard`, same border styleSheet
- Inside: `QVBoxLayout` spacing 0:
  - `QLabel` named `aggsCardHeader`, text `"AGGREGATES"`, same header styleSheet
  - `QWidget` named `aggsContent`, `QGridLayout` (margins 6/4/6/6, spacing 4):
    - Row 0 col 0: `QLabel` text `"Total"`, small grey label style
    - Row 0 col 1: `QLabel` named `statsTotalCount`, text `"—"`, readout style (`font-size: 16px; font-weight: 700;`)
    - Row 1 col 0: `QLabel` text `"Avg Conf"`, small grey label style  
    - Row 1 col 1: `QLabel` named `statsAvgConf`, text `"—"`, readout style

Add a vertical `QSpacerItem` at the bottom of `statsSidebar`.

**Full-width table section**: Keep the existing `groupData` `QGroupBox` with `resultsTable` — move it below `topSection` in `verticalLayout_main`.

Save the `.ui` file.

- [ ] **Step 3: Verify structural integrity**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -c "
from PyQt6 import QtWidgets, uic
import sys
app = QtWidgets.QApplication(sys.argv)

import mpcamera.ui.results_window  # imports QMainWindow subclass
w = mpcamera.ui.results_window.ResultsWindow()

for name in ['imageTabWidget','tabFullImage','tabParticle','fullImageView','previewView',
             'statsSidebar','distCard','distFragmentCount','distFiberCount',
             'statsTotalCount','statsAvgConf','resultsHeaderBar','resultsBreadcrumb']:
    widget = w.findChild(QtWidgets.QWidget, name)
    assert widget is not None, f'{name} missing'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add mpcamera/layouts/resultsWindow.ui
git commit -m "feat(ui): add header bar, tabbed image panel, and stats sidebar to results window"
```

---

## Task 6: Results Window Controller — Tab Switching + Stats Sidebar

**Files:**
- Modify: `mpcamera/ui/results_window.py`
- Create: `tests/test_results_tab_switch.py`

- [ ] **Step 1: Write failing tests** in `tests/test_results_tab_switch.py`:

```python
# tests/test_results_tab_switch.py
"""Tests for tab switching and stats sidebar in ResultsWindow."""
import pytest
from unittest.mock import MagicMock, patch
from PyQt6 import QtWidgets, QtGui, QtCore


@pytest.fixture
def app(qtbot):
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def results_window(app, qtbot):
    from mpcamera.ui.results_window import ResultsWindow
    w = ResultsWindow()
    qtbot.addWidget(w)
    return w


def _make_pixmap(w=100, h=100):
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtGui.QColor("#cccccc"))
    return pm


def _make_preds(n=3):
    return [
        {
            "label": "Fragment" if i % 2 == 0 else "Fiber",
            "score": 0.90,
            "points": [[10, 10], [30, 10], [30, 30], [10, 30]],
            "bbox": [10, 10, 20, 20],
        }
        for i in range(n)
    ]


def test_selecting_row_switches_to_particle_tab(results_window, qtbot):
    """Clicking a table row switches imageTabWidget to the particle tab (index 1)."""
    preds = _make_preds(3)
    pixmap = _make_pixmap()
    results_window.update_data(preds, pixmap, None)

    tab = results_window.findChild(QtWidgets.QTabWidget, "imageTabWidget")
    assert tab is not None

    # Start on full image tab (index 0)
    tab.setCurrentIndex(0)

    # Select first row
    results_window.table.selectRow(0)

    assert tab.currentIndex() == 1, "Should have switched to particle tab on row selection"


def test_stats_sidebar_total_count_after_update(results_window, qtbot):
    """stats sidebar total count label shows number of predictions after update_data."""
    preds = _make_preds(5)
    pixmap = _make_pixmap()
    results_window.update_data(preds, pixmap, None)

    total_lbl = results_window.findChild(QtWidgets.QLabel, "statsTotalCount")
    assert total_lbl is not None
    assert total_lbl.text() == "5"


def test_stats_sidebar_fragment_count(results_window, qtbot):
    """distFragmentCount label shows correct count after update_data."""
    preds = _make_preds(4)  # labels alternate Fragment/Fiber → 2 fragments
    pixmap = _make_pixmap()
    results_window.update_data(preds, pixmap, None)

    frag_lbl = results_window.findChild(QtWidgets.QLabel, "distFragmentCount")
    assert frag_lbl is not None
    assert frag_lbl.text() == "2"


def test_full_image_tab_shows_annotated_pixmap(results_window, qtbot):
    """After update_data, fullImageView has a scene with content."""
    preds = _make_preds(2)
    pixmap = _make_pixmap()
    results_window.update_data(preds, pixmap, None)

    full_view = results_window.findChild(QtWidgets.QGraphicsView, "fullImageView")
    assert full_view is not None
    assert full_view.scene() is not None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -m pytest tests/test_results_tab_switch.py -v
```

Expected: multiple FAILs (methods not yet implemented).

- [ ] **Step 3: Update widget references in `ResultsWindow.__init__`**

In `results_window.py`, replace the widget reference block (lines 98–102) with:

```python
        # --- 2. Widget References ---
        self.table: QtWidgets.QTableWidget = getattr(self, "resultsTable", None)
        self.preview_view: QtWidgets.QGraphicsView = getattr(self, "previewView", None)
        self.full_image_view: QtWidgets.QGraphicsView = getattr(self, "fullImageView", None)
        self.image_tab_widget: QtWidgets.QTabWidget = getattr(self, "imageTabWidget", None)
        self.btn_delete: QtWidgets.QPushButton = getattr(self, "btnDelete", None)
        self.btn_save: QtWidgets.QPushButton = getattr(self, "btnSave", None)
        self.splitter: QtWidgets.QSplitter = getattr(self, "splitter", None)

        # Stats sidebar labels
        self._stats_total = getattr(self, "statsTotalCount", None)
        self._stats_avg_conf = getattr(self, "statsAvgConf", None)
        self._dist_labels: dict[str, QtWidgets.QLabel] = {
            "Fragment": getattr(self, "distFragmentCount", None),
            "Fiber":    getattr(self, "distFiberCount", None),
            "Film":     getattr(self, "distFilmCount", None),
            "Foam":     getattr(self, "distFoamCount", None),
            "Pellet":   getattr(self, "distPelletCount", None),
            "Sheet":    getattr(self, "distSheetCount", None),
            "Bead":     getattr(self, "distBeadCount", None),
        }
```

- [ ] **Step 4: Set up `fullImageView` graphics controller in `__init__`**

After the existing `_PreviewController` setup block (around line 118), add:

```python
        # --- 3b. Setup Full Image View ---
        if self.full_image_view is not None:
            self.full_image_view.setDragMode(
                QtWidgets.QGraphicsView.DragMode.ScrollHandDrag
            )
            self.full_image_view.setTransformationAnchor(
                QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
            )
            self._full_image_ctrl = _PreviewController(self.full_image_view)
        else:
            self._full_image_ctrl = None
```

- [ ] **Step 5: Switch to particle tab in `_on_selection_changed`**

At the top of the existing `_on_selection_changed` method (line 362), add after the early-return checks:

```python
        # Switch to the particle preview tab
        if self.image_tab_widget is not None:
            self.image_tab_widget.setCurrentIndex(1)
            # Update tab label to show particle ID
            try:
                self.image_tab_widget.setTabText(1, f"Particle {row + 1:03d}")
            except Exception:
                pass
```

- [ ] **Step 6: Add `_update_stats_sidebar` method**

Add this method after `update_data`:

```python
    def _update_stats_sidebar(self, preds: list) -> None:
        """Populate the stats sidebar with aggregate counts from preds."""
        count = len(preds)

        if self._stats_total is not None:
            self._stats_total.setText(str(count) if count else "—")

        avg_conf = (
            sum(p.get("score", 0) for p in preds) / count if count else 0.0
        )
        if self._stats_avg_conf is not None:
            self._stats_avg_conf.setText(f"{avg_conf:.2f}" if count else "—")

        # Per-class distribution
        from collections import Counter
        class_counts = Counter(p.get("label", "Fragment") for p in preds)
        for label, lbl_widget in self._dist_labels.items():
            if lbl_widget is not None:
                c = class_counts.get(label, 0)
                lbl_widget.setText(str(c) if count else "—")
```

- [ ] **Step 7: Call `_update_stats_sidebar` and set full image in `update_data`**

In `update_data` (line ~155), after `self._cached_morphometrics = []`, add:

```python
        # Update stats sidebar
        try:
            self._update_stats_sidebar(preds or [])
        except Exception as e:
            print(f"[RESULTS] Stats sidebar update failed: {e}")

        # Show full annotated image in the Full Image tab
        if last_pixmap is not None and self._full_image_ctrl is not None:
            try:
                self._full_image_ctrl.setPixmap(last_pixmap)
                # Switch to full image tab when new data arrives
                if self.image_tab_widget is not None:
                    self.image_tab_widget.setCurrentIndex(0)
                    self.image_tab_widget.setTabText(1, "Particle —")
            except Exception:
                pass
```

- [ ] **Step 8: Apply shared QSS to table header**

At the end of `__init__`, add:

```python
        # Apply instrument-panel table header style
        from mpcamera.ui.styles import TABLE_HEADER_QSS
        try:
            if self.table is not None:
                self.table.horizontalHeader().setStyleSheet(TABLE_HEADER_QSS)
        except Exception:
            pass
```

- [ ] **Step 9: Update `resultsBreadcrumb` when the window is opened**

`ResultsWindow` is instantiated per-inference in `camera_page.py`. Add a `set_breadcrumb` method:

```python
    def set_breadcrumb(self, farm: str, sample: str) -> None:
        """Set the header breadcrumb (called by CameraPageController before show())."""
        lbl = getattr(self, "resultsBreadcrumb", None)
        if lbl is not None:
            lbl.setText(f"{farm}  /  {sample}")
```

In `camera_page.py`, find where `ResultsWindow` is created and shown (search for `ResultsWindow()`), and call `set_breadcrumb` before `show()`:

```python
            # Set breadcrumb from current selections
            try:
                farm = self.ui["farm_combo"].currentText() if self.ui.get("farm_combo") else "—"
                sample = self.ui["soil_combo"].currentText() if self.ui.get("soil_combo") else "—"
                self._large_table_window.set_breadcrumb(farm, sample)
            except Exception:
                pass
```

- [ ] **Step 10: Run all tests — verify they pass**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -m pytest tests/ -v
```

Expected:
```
PASSED tests/test_last_run_panel.py::test_last_run_panel_updates_particle_count
PASSED tests/test_last_run_panel.py::test_last_run_panel_shows_dashes_when_empty
PASSED tests/test_results_tab_switch.py::test_selecting_row_switches_to_particle_tab
PASSED tests/test_results_tab_switch.py::test_stats_sidebar_total_count_after_update
PASSED tests/test_results_tab_switch.py::test_stats_sidebar_fragment_count
PASSED tests/test_results_tab_switch.py::test_full_image_tab_shows_annotated_pixmap
```

- [ ] **Step 11: Commit**

```bash
git add mpcamera/ui/results_window.py tests/test_results_tab_switch.py
git commit -m "feat: wire tab switching, stats sidebar, and breadcrumb in results window"
```

---

## Task 7: Apply Class Badge Styling to Results Table

**Files:**
- Modify: `mpcamera/ui/results_window.py`

The Class column currently uses a `QComboBox` cell widget. Wrap the combo in a styled container or add a colored indicator beside it.

- [ ] **Step 1: Add `_badge_color_for_label` helper to `results_window.py`**

Add this static method inside `ResultsWindow`:

```python
    @staticmethod
    def _badge_color_for_label(label: str) -> tuple[str, str]:
        """Return (background_hex, text_hex) for a class label badge."""
        from mpcamera.ui.styles import CLASS_BADGE_COLORS
        return CLASS_BADGE_COLORS.get(label.lower(), ("#f3f4f6", "#374151"))
```

- [ ] **Step 2: Color the row background based on class in `update_data`**

In `update_data`, after `self.table.setCellWidget(i, 1, combo)` (around line 228), add:

```python
            # Tint the ID item with badge background color for visual class identification
            try:
                bg_hex, _ = ResultsWindow._badge_color_for_label(current_label)
                id_item = self.table.item(i, 0)
                if id_item is not None:
                    id_item.setBackground(QtGui.QBrush(QtGui.QColor(bg_hex)))
            except Exception:
                pass
```

- [ ] **Step 3: Highlight the Area column (col 4) in blue**

After the loop that sets metric items (after line 248), add:

```python
            # Highlight area value in blue (primary metric)
            try:
                area_item = self.table.item(i, 4)
                if area_item is not None:
                    area_item.setForeground(QtGui.QBrush(QtGui.QColor("#2563eb")))
            except Exception:
                pass
```

- [ ] **Step 4: Run tests to confirm nothing broke**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -m pytest tests/ -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add mpcamera/ui/results_window.py
git commit -m "feat: add class badge colors and area column highlight to results table"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|---|---|
| Shared design language: section chrome, tabular-nums, class badges | Task 1, 6, 7 |
| Camera page header bar (two-row title, status badge, breadcrumb) | Task 2, 4 |
| Camera page 3-column layout (sliders, feed, instrument panel) | Task 3 |
| Instrument panel: MODEL, THRESHOLDS readouts, RUN INFERENCE, LAST RUN | Task 3, 4 |
| Results window header bar | Task 5 |
| Results window tabbed image panel (Full Image ↔ Particle [ID]) | Task 5, 6 |
| Row selection → switch to particle tab | Task 6 |
| Stats sidebar: distribution counts + aggregates | Task 5, 6 |
| Table: instrument-style column headers | Task 6 |
| Table: class badge colors (ID cell tint) | Task 7 |
| Table: area column highlighted blue | Task 7 |
| Save button only in results footer (not header) | Task 5 (header has no Save) |
| Breadcrumb set from farm/sample selection | Task 4, 6 |
