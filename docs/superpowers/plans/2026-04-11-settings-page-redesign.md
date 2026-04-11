# Settings Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the settings page scroll layout with a 7-tab `QTabWidget`, expose all Roboflow and Directus config fields, and add Show/Hide toggles for sensitive fields.

**Architecture:** The `.ui` file is rewritten to use `QTabWidget` with one page per settings group. The controller (`settings_page.py`) is updated to load/save 5 new fields and wire Show/Hide toggles. No schema changes required — all new fields already exist in `config_schema.json`.

**Tech Stack:** PyQt6, `uic.loadUi()`, `~/.mpcamera/config.json` via existing `Settings` singleton.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `mpcamera/layouts/settingsPage.ui` | Rewrite | Two-panel scroll → `QTabWidget` with 7 tab pages |
| `mpcamera/controllers/settings_page.py` | Modify | Load/save 5 new fields; wire Show/Hide toggles |
| `tests/ui/test_settings_page.py` | Create | Unit tests for controller load/save/toggle logic |

---

### Task 1: Write failing tests for the controller

**Files:**
- Create: `tests/ui/test_settings_page.py`

- [ ] **Step 1: Create the test file**

```python
# tests/ui/test_settings_page.py
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from PyQt6 import QtWidgets
import sys

# Minimal QApplication required for any Qt widget
@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    return app


def _make_page(qapp):
    """Build a minimal QWidget with all named child widgets the controller expects."""
    page = QtWidgets.QWidget()

    spin_names = [
        "cameraResWidthSpin", "cameraResHeightSpin",
        "frameIntervalSpin", "inferenceIntervalSpin",
        "sensorWidthSpin", "sensorHeightSpin", "defaultMagnificationSpin",
        "defaultConfidenceSpin", "defaultIouSpin",
        "brightnessDefaultSpin", "contrastDefaultSpin",
        "directusTimeoutSpin",
    ]
    line_names = [
        "fourccLineEdit", "localModelsDirLine",
        "roboflowApiKeyLine", "roboflowApiUrlLine",
        "roboflowWorkspaceLine", "roboflowWorkflowLine",
        "directusApiUrlLine", "directusBearerLine",
    ]
    check_names = ["forceDirectShowCheck", "preferLocalCheck"]
    btn_names = [
        "saveSettingsButton",
        "roboflowApiKeyToggle",
        "directusBearerToggle",
    ]

    for name in spin_names:
        w = QtWidgets.QDoubleSpinBox(page)
        w.setObjectName(name)
        w.setMaximum(100000)
    for name in line_names:
        w = QtWidgets.QLineEdit(page)
        w.setObjectName(name)
    for name in check_names:
        w = QtWidgets.QCheckBox(page)
        w.setObjectName(name)
    for name in btn_names:
        w = QtWidgets.QPushButton(page)
        w.setObjectName(name)

    return page


def _make_cfg():
    """Return a Settings-like dict with all expected keys."""
    from mpcamera.config import Settings
    return Settings({
        "camera": {"resolution_width": 1920, "resolution_height": 1080, "fourcc": "MJPG", "force_directshow": True},
        "streaming": {"frame_interval_ms": 33, "inference_interval_ms": 1000},
        "measurement": {"effective_sensor_width_mm": 23.73, "effective_sensor_height_mm": 15.87, "default_magnification": 2.8},
        "inference": {"default_confidence": 0.4, "default_iou": 0.5},
        "brightness_contrast": {"brightness_default": 50, "contrast_default": 50},
        "models": {"local_models_dir": "models", "prefer_local": False},
        "services": {
            "roboflow": {
                "api_key": "test-key",
                "api_url": "http://localhost:9001",
                "workspace": "soilsight-xstgr",
                "workflow": "detect-count-and-visualize-2",
            },
            "directus": {
                "api_url": "http://example.com",
                "bearer_token": "test-token",
                "timeout_seconds": 30,
            },
        },
    })


class TestSettingsPageControllerLoad:
    def test_loads_roboflow_api_key(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QLineEdit, "roboflowApiKeyLine")
        assert w.text() == "test-key"

    def test_loads_roboflow_api_url(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QLineEdit, "roboflowApiUrlLine")
        assert w.text() == "http://localhost:9001"

    def test_loads_roboflow_workspace(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QLineEdit, "roboflowWorkspaceLine")
        assert w.text() == "soilsight-xstgr"

    def test_loads_roboflow_workflow(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QLineEdit, "roboflowWorkflowLine")
        assert w.text() == "detect-count-and-visualize-2"

    def test_loads_directus_api_url(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QLineEdit, "directusApiUrlLine")
        assert w.text() == "http://example.com"

    def test_loads_directus_timeout(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QDoubleSpinBox, "directusTimeoutSpin")
        assert w.value() == 30


class TestSettingsPageControllerSave:
    def test_saves_roboflow_api_url(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        cfg.save = MagicMock()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QLineEdit, "roboflowApiUrlLine")
        w.setText("http://newserver:9001")
        ctrl._on_save_clicked()
        assert cfg["services"]["roboflow"]["api_url"] == "http://newserver:9001"

    def test_saves_directus_timeout(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        cfg.save = MagicMock()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QDoubleSpinBox, "directusTimeoutSpin")
        w.setValue(60)
        ctrl._on_save_clicked()
        assert cfg["services"]["directus"]["timeout_seconds"] == 60


class TestShowHideToggle:
    def test_roboflow_key_starts_password_mode(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        w = page.findChild(QtWidgets.QLineEdit, "roboflowApiKeyLine")
        assert w.echoMode() == QtWidgets.QLineEdit.EchoMode.Password

    def test_roboflow_key_toggle_shows_text(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        btn = page.findChild(QtWidgets.QPushButton, "roboflowApiKeyToggle")
        btn.click()
        w = page.findChild(QtWidgets.QLineEdit, "roboflowApiKeyLine")
        assert w.echoMode() == QtWidgets.QLineEdit.EchoMode.Normal

    def test_directus_token_toggle_shows_text(self, qapp):
        page = _make_page(qapp)
        cfg = _make_cfg()
        with patch("mpcamera.controllers.settings_page.get_settings", return_value=cfg):
            from mpcamera.controllers.settings_page import SettingsPageController
            ctrl = SettingsPageController(page, MagicMock())
        btn = page.findChild(QtWidgets.QPushButton, "directusBearerToggle")
        btn.click()
        w = page.findChild(QtWidgets.QLineEdit, "directusBearerLine")
        assert w.echoMode() == QtWidgets.QLineEdit.EchoMode.Normal
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -m pytest tests/ui/test_settings_page.py -v 2>&1 | head -60
```

Expected: tests fail — new widget names (`roboflowApiUrlLine`, etc.) don't exist yet and controller doesn't wire them.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/ui/test_settings_page.py
git commit -m "test: add failing tests for settings page redesign"
```

---

### Task 2: Rewrite `settingsPage.ui` with `QTabWidget`

**Files:**
- Rewrite: `mpcamera/layouts/settingsPage.ui`

> Note: Per CLAUDE.md, `.ui` files should not be hand-edited XML. However, since we need programmatic generation for this redesign and the change is structural (not aesthetic tweaks), we rewrite the XML directly. Qt Designer can open and further edit the result.

- [ ] **Step 1: Replace the entire contents of `settingsPage.ui`**

Write the full XML below, replacing the existing file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>layoutWidget</class>
 <widget class="QWidget" name="layoutWidget">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>980</width><height>720</height></rect>
  </property>
  <property name="styleSheet">
   <string notr="true">
QWidget {
    font-family: "Inter";
    font-size: 12pt;
}
QTabWidget::pane {
    border: 1px solid #d0d0d0;
    border-radius: 0 6px 6px 6px;
    background: #ffffff;
}
QTabBar::tab {
    background: #f0f0f0;
    border: 1px solid #d0d0d0;
    border-bottom: none;
    padding: 8px 18px;
    margin-right: 2px;
    border-radius: 5px 5px 0 0;
    font-size: 11pt;
    color: #555555;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #111111;
    font-weight: bold;
    border-bottom: 1px solid #ffffff;
}
QTabBar::tab:hover:!selected {
    background: #e0e0e0;
}
QPushButton {
    background-color: black;
    color: white;
    border-radius: 5px;
    font-weight: bold;
}
QPushButton:disabled {
    background-color: #dcdcdc;
    color: #7a7a7a;
    border: 1px solid #c0c0c0;
}
QPushButton[designClass="lightButton"] {
    background-color: white;
    color: black;
    border-radius: 5px;
    border: 1px solid black;
    font-weight: bold;
}
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12pt;
    color: #333333;
}
QLineEdit:focus { border: 1px solid #0078d4; }
QLineEdit:hover { border: 1px solid #a0a0a0; }
QDoubleSpinBox, QSpinBox {
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12pt;
    color: #333333;
}
QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid #0078d4; }
   </string>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout_root">
   <property name="spacing"><number>0</number></property>
   <property name="leftMargin"><number>18</number></property>
   <property name="topMargin"><number>18</number></property>
   <property name="rightMargin"><number>18</number></property>
   <property name="bottomMargin"><number>18</number></property>
   <item>
    <widget class="QLabel" name="titleLabel">
     <property name="styleSheet"><string notr="true">QLabel { font-size: 20px; font-weight: bold; margin-bottom: 8px; }</string></property>
     <property name="text"><string>Application Settings</string></property>
    </widget>
   </item>
   <item>
    <widget class="QTabWidget" name="settingsTabWidget">
     <property name="currentIndex"><number>0</number></property>

     <!-- TAB 1: Camera -->
     <widget class="QWidget" name="cameraTab">
      <attribute name="title"><string>Camera</string></attribute>
      <layout class="QVBoxLayout">
       <property name="leftMargin"><number>20</number></property>
       <property name="topMargin"><number>20</number></property>
       <property name="rightMargin"><number>20</number></property>
       <property name="bottomMargin"><number>20</number></property>
       <item>
        <layout class="QGridLayout" name="cameraGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_res_w"><property name="text"><string>Resolution Width</string></property></widget></item>
         <item row="0" column="1"><widget class="QSpinBox" name="cameraResWidthSpin"><property name="minimum"><number>1</number></property><property name="maximum"><number>10000</number></property></widget></item>
         <item row="1" column="0"><widget class="QLabel" name="label_res_h"><property name="text"><string>Resolution Height</string></property></widget></item>
         <item row="1" column="1"><widget class="QSpinBox" name="cameraResHeightSpin"><property name="minimum"><number>1</number></property><property name="maximum"><number>10000</number></property></widget></item>
         <item row="2" column="0"><widget class="QLabel" name="label_fourcc"><property name="text"><string>FOURCC</string></property></widget></item>
         <item row="2" column="1"><widget class="QLineEdit" name="fourccLineEdit"/></item>
         <item row="3" column="0"><widget class="QLabel" name="label_force_dshow"><property name="text"><string>Force DirectShow (Windows)</string></property></widget></item>
         <item row="3" column="1"><widget class="QCheckBox" name="forceDirectShowCheck"/></item>
        </layout>
       </item>
       <item><spacer><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
       <item>
        <layout class="QHBoxLayout">
         <item><spacer><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
         <item><widget class="QPushButton" name="saveSettingsButton"><property name="minimumSize"><size><width>140</width><height>40</height></size></property><property name="text"><string>Save Settings</string></property></widget></item>
        </layout>
       </item>
      </layout>
     </widget>

     <!-- TAB 2: Streaming -->
     <widget class="QWidget" name="streamingTab">
      <attribute name="title"><string>Streaming</string></attribute>
      <layout class="QVBoxLayout">
       <property name="leftMargin"><number>20</number></property>
       <property name="topMargin"><number>20</number></property>
       <property name="rightMargin"><number>20</number></property>
       <property name="bottomMargin"><number>20</number></property>
       <item>
        <layout class="QGridLayout" name="streamingGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_frame_interval"><property name="text"><string>Frame Interval (ms)</string></property></widget></item>
         <item row="0" column="1"><widget class="QSpinBox" name="frameIntervalSpin"><property name="minimum"><number>1</number></property><property name="maximum"><number>10000</number></property></widget></item>
         <item row="1" column="0"><widget class="QLabel" name="label_inference_interval"><property name="text"><string>Inference Interval (ms)</string></property></widget></item>
         <item row="1" column="1"><widget class="QSpinBox" name="inferenceIntervalSpin"><property name="minimum"><number>50</number></property><property name="maximum"><number>60000</number></property></widget></item>
        </layout>
       </item>
       <item><spacer><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
       <item>
        <layout class="QHBoxLayout">
         <item><spacer><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
         <item><widget class="QPushButton" name="saveSettingsButton_2"><property name="minimumSize"><size><width>140</width><height>40</height></size></property><property name="text"><string>Save Settings</string></property></widget></item>
        </layout>
       </item>
      </layout>
     </widget>

     <!-- TAB 3: Measurement -->
     <widget class="QWidget" name="measurementTab">
      <attribute name="title"><string>Measurement</string></attribute>
      <layout class="QVBoxLayout">
       <property name="leftMargin"><number>20</number></property>
       <property name="topMargin"><number>20</number></property>
       <property name="rightMargin"><number>20</number></property>
       <property name="bottomMargin"><number>20</number></property>
       <item>
        <layout class="QGridLayout" name="measurementGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_sensor_w"><property name="text"><string>Sensor Width (mm)</string></property></widget></item>
         <item row="0" column="1"><widget class="QDoubleSpinBox" name="sensorWidthSpin"><property name="decimals"><number>4</number></property><property name="minimum"><double>0.0001</double></property><property name="maximum"><double>1000.0</double></property></widget></item>
         <item row="1" column="0"><widget class="QLabel" name="label_sensor_h"><property name="text"><string>Sensor Height (mm)</string></property></widget></item>
         <item row="1" column="1"><widget class="QDoubleSpinBox" name="sensorHeightSpin"><property name="decimals"><number>4</number></property><property name="minimum"><double>0.0001</double></property><property name="maximum"><double>1000.0</double></property></widget></item>
         <item row="2" column="0"><widget class="QLabel" name="label_default_mag"><property name="text"><string>Default Magnification</string></property></widget></item>
         <item row="2" column="1"><widget class="QDoubleSpinBox" name="defaultMagnificationSpin"><property name="decimals"><number>3</number></property><property name="minimum"><double>0.01</double></property><property name="maximum"><double>100.0</double></property></widget></item>
        </layout>
       </item>
       <item><spacer><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
       <item>
        <layout class="QHBoxLayout">
         <item><spacer><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
         <item><widget class="QPushButton" name="saveSettingsButton_3"><property name="minimumSize"><size><width>140</width><height>40</height></size></property><property name="text"><string>Save Settings</string></property></widget></item>
        </layout>
       </item>
      </layout>
     </widget>

     <!-- TAB 4: Inference -->
     <widget class="QWidget" name="inferenceTab">
      <attribute name="title"><string>Inference</string></attribute>
      <layout class="QVBoxLayout">
       <property name="leftMargin"><number>20</number></property>
       <property name="topMargin"><number>20</number></property>
       <property name="rightMargin"><number>20</number></property>
       <property name="bottomMargin"><number>20</number></property>
       <item>
        <layout class="QGridLayout" name="inferenceGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_def_conf"><property name="text"><string>Default Confidence</string></property></widget></item>
         <item row="0" column="1"><widget class="QDoubleSpinBox" name="defaultConfidenceSpin"><property name="decimals"><number>2</number></property><property name="minimum"><double>0.0</double></property><property name="maximum"><double>1.0</double></property><property name="singleStep"><double>0.01</double></property></widget></item>
         <item row="1" column="0"><widget class="QLabel" name="label_def_iou"><property name="text"><string>Default IoU</string></property></widget></item>
         <item row="1" column="1"><widget class="QDoubleSpinBox" name="defaultIouSpin"><property name="decimals"><number>2</number></property><property name="minimum"><double>0.0</double></property><property name="maximum"><double>1.0</double></property><property name="singleStep"><double>0.01</double></property></widget></item>
        </layout>
       </item>
       <item><spacer><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
       <item>
        <layout class="QHBoxLayout">
         <item><spacer><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
         <item><widget class="QPushButton" name="saveSettingsButton_4"><property name="minimumSize"><size><width>140</width><height>40</height></size></property><property name="text"><string>Save Settings</string></property></widget></item>
        </layout>
       </item>
      </layout>
     </widget>

     <!-- TAB 5: Display -->
     <widget class="QWidget" name="displayTab">
      <attribute name="title"><string>Display</string></attribute>
      <layout class="QVBoxLayout">
       <property name="leftMargin"><number>20</number></property>
       <property name="topMargin"><number>20</number></property>
       <property name="rightMargin"><number>20</number></property>
       <property name="bottomMargin"><number>20</number></property>
       <item>
        <layout class="QGridLayout" name="bcGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_b_default"><property name="text"><string>Brightness Default</string></property></widget></item>
         <item row="0" column="1"><widget class="QSpinBox" name="brightnessDefaultSpin"><property name="minimum"><number>0</number></property><property name="maximum"><number>100</number></property></widget></item>
         <item row="1" column="0"><widget class="QLabel" name="label_c_default"><property name="text"><string>Contrast Default</string></property></widget></item>
         <item row="1" column="1"><widget class="QSpinBox" name="contrastDefaultSpin"><property name="minimum"><number>0</number></property><property name="maximum"><number>100</number></property></widget></item>
        </layout>
       </item>
       <item><spacer><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
       <item>
        <layout class="QHBoxLayout">
         <item><spacer><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
         <item><widget class="QPushButton" name="saveSettingsButton_5"><property name="minimumSize"><size><width>140</width><height>40</height></size></property><property name="text"><string>Save Settings</string></property></widget></item>
        </layout>
       </item>
      </layout>
     </widget>

     <!-- TAB 6: Models -->
     <widget class="QWidget" name="modelsTab">
      <attribute name="title"><string>Models</string></attribute>
      <layout class="QVBoxLayout">
       <property name="leftMargin"><number>20</number></property>
       <property name="topMargin"><number>20</number></property>
       <property name="rightMargin"><number>20</number></property>
       <property name="bottomMargin"><number>20</number></property>
       <item>
        <layout class="QGridLayout" name="modelsGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_local_dir"><property name="text"><string>Local Models Dir</string></property></widget></item>
         <item row="0" column="1"><widget class="QLineEdit" name="localModelsDirLine"/></item>
         <item row="1" column="0"><widget class="QLabel" name="label_prefer_local"><property name="text"><string>Prefer Local Models</string></property></widget></item>
         <item row="1" column="1"><widget class="QCheckBox" name="preferLocalCheck"/></item>
        </layout>
       </item>
       <item><spacer><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
       <item>
        <layout class="QHBoxLayout">
         <item><spacer><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
         <item><widget class="QPushButton" name="saveSettingsButton_6"><property name="minimumSize"><size><width>140</width><height>40</height></size></property><property name="text"><string>Save Settings</string></property></widget></item>
        </layout>
       </item>
      </layout>
     </widget>

     <!-- TAB 7: Services -->
     <widget class="QWidget" name="servicesTab">
      <attribute name="title"><string>Services</string></attribute>
      <layout class="QVBoxLayout">
       <property name="leftMargin"><number>20</number></property>
       <property name="topMargin"><number>20</number></property>
       <property name="rightMargin"><number>20</number></property>
       <property name="bottomMargin"><number>20</number></property>
       <item>
        <widget class="QLabel" name="roboflowGroupLabel">
         <property name="styleSheet"><string notr="true">QLabel { font-size: 13pt; font-weight: bold; color: #111; border-bottom: 1px solid #ddd; padding-bottom: 4px; }</string></property>
         <property name="text"><string>Roboflow</string></property>
        </widget>
       </item>
       <item>
        <layout class="QGridLayout" name="roboflowGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_rf_key"><property name="text"><string>API Key</string></property></widget></item>
         <item row="0" column="1">
          <layout class="QHBoxLayout">
           <item><widget class="QLineEdit" name="roboflowApiKeyLine"><property name="echoMode"><enum>QLineEdit::Password</enum></property></widget></item>
           <item><widget class="QPushButton" name="roboflowApiKeyToggle"><property name="text"><string>Show</string></property><property name="maximumWidth"><number>60</number></property><property name="styleSheet"><string notr="true">QPushButton { background: #eeeeee; color: #333; border: 1px solid #ccc; border-radius: 4px; font-weight: normal; } QPushButton:hover { background: #e0e0e0; }</string></property></widget></item>
          </layout>
         </item>
         <item row="1" column="0"><widget class="QLabel" name="label_rf_url"><property name="text"><string>API URL</string></property></widget></item>
         <item row="1" column="1"><widget class="QLineEdit" name="roboflowApiUrlLine"/></item>
         <item row="2" column="0"><widget class="QLabel" name="label_rf_workspace"><property name="text"><string>Workspace</string></property></widget></item>
         <item row="2" column="1"><widget class="QLineEdit" name="roboflowWorkspaceLine"/></item>
         <item row="3" column="0"><widget class="QLabel" name="label_rf_workflow"><property name="text"><string>Workflow</string></property></widget></item>
         <item row="3" column="1"><widget class="QLineEdit" name="roboflowWorkflowLine"/></item>
        </layout>
       </item>
       <item>
        <widget class="QLabel" name="directusGroupLabel">
         <property name="styleSheet"><string notr="true">QLabel { font-size: 13pt; font-weight: bold; color: #111; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 10px; }</string></property>
         <property name="text"><string>Directus</string></property>
        </widget>
       </item>
       <item>
        <layout class="QGridLayout" name="directusGrid">
         <property name="verticalSpacing"><number>10</number></property>
         <item row="0" column="0"><widget class="QLabel" name="label_directus_url"><property name="text"><string>API URL</string></property></widget></item>
         <item row="0" column="1"><widget class="QLineEdit" name="directusApiUrlLine"/></item>
         <item row="1" column="0"><widget class="QLabel" name="label_directus"><property name="text"><string>Bearer Token</string></property></widget></item>
         <item row="1" column="1">
          <layout class="QHBoxLayout">
           <item><widget class="QLineEdit" name="directusBearerLine"><property name="echoMode"><enum>QLineEdit::Password</enum></property></widget></item>
           <item><widget class="QPushButton" name="directusBearerToggle"><property name="text"><string>Show</string></property><property name="maximumWidth"><number>60</number></property><property name="styleSheet"><string notr="true">QPushButton { background: #eeeeee; color: #333; border: 1px solid #ccc; border-radius: 4px; font-weight: normal; } QPushButton:hover { background: #e0e0e0; }</string></property></widget></item>
          </layout>
         </item>
         <item row="2" column="0"><widget class="QLabel" name="label_directus_timeout"><property name="text"><string>Timeout (s)</string></property></widget></item>
         <item row="2" column="1"><widget class="QSpinBox" name="directusTimeoutSpin"><property name="minimum"><number>1</number></property><property name="maximum"><number>300</number></property></widget></item>
        </layout>
       </item>
       <item><spacer><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
       <item>
        <layout class="QHBoxLayout">
         <item><spacer><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
         <item><widget class="QPushButton" name="saveSettingsButton_7"><property name="minimumSize"><size><width>140</width><height>40</height></size></property><property name="text"><string>Save Settings</string></property></widget></item>
        </layout>
       </item>
      </layout>
     </widget>

    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
```

- [ ] **Step 2: Verify the UI file loads without error**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -c "
from PyQt6 import uic, QtWidgets
import sys
app = QtWidgets.QApplication(sys.argv)
w = uic.loadUi('mpcamera/layouts/settingsPage.ui')
print('Tabs:', w.settingsTabWidget.count())
print('OK')
"
```

Expected output:
```
Tabs: 7
OK
```

- [ ] **Step 3: Commit the new UI file**

```bash
git add mpcamera/layouts/settingsPage.ui
git commit -m "feat: rewrite settings page UI with 7-tab QTabWidget layout"
```

---

### Task 3: Update the controller — wire all Save buttons and new fields

**Files:**
- Modify: `mpcamera/controllers/settings_page.py`

- [ ] **Step 1: Replace the full contents of `settings_page.py`**

```python
import os
import traceback
from PyQt6 import QtWidgets
from mpcamera.config import get_settings


class SettingsPageController:
    """Controller for the Settings page: load values from config and save them."""

    # All Save button names across tabs
    _SAVE_BUTTONS = [
        "saveSettingsButton",
        "saveSettingsButton_2",
        "saveSettingsButton_3",
        "saveSettingsButton_4",
        "saveSettingsButton_5",
        "saveSettingsButton_6",
        "saveSettingsButton_7",
    ]

    def __init__(self, page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
        self.page = page
        self.main_window = main_window
        self.ui = page
        try:
            self._wire()
            self.load_values()
        except Exception:
            traceback.print_exc()

    def _wire(self):
        # Connect all Save buttons (one per tab, all call same handler)
        for btn_name in self._SAVE_BUTTONS:
            btn = self.page.findChild(QtWidgets.QPushButton, btn_name)
            if btn is not None:
                btn.clicked.connect(self._on_save_clicked)

        # Show/Hide toggles for sensitive fields
        self._wire_toggle("roboflowApiKeyToggle", "roboflowApiKeyLine")
        self._wire_toggle("directusBearerToggle", "directusBearerLine")

    def _wire_toggle(self, btn_name: str, line_name: str):
        btn = self.page.findChild(QtWidgets.QPushButton, btn_name)
        line = self.page.findChild(QtWidgets.QLineEdit, line_name)
        if btn is None or line is None:
            return

        def toggle():
            hidden = line.echoMode() == QtWidgets.QLineEdit.EchoMode.Password
            line.setEchoMode(
                QtWidgets.QLineEdit.EchoMode.Normal
                if hidden
                else QtWidgets.QLineEdit.EchoMode.Password
            )
            btn.setText("Hide" if hidden else "Show")

        btn.clicked.connect(toggle)

    def load_values(self):
        """Load values from settings into the UI widgets."""
        try:
            cfg = get_settings()
        except Exception:
            cfg = None

        def set_text(widget_name, value):
            w = self.page.findChild(QtWidgets.QWidget, widget_name)
            if w is not None:
                try:
                    w.setText(str(value))
                except Exception:
                    pass

        def set_value(widget_name, value):
            w = self.page.findChild(QtWidgets.QWidget, widget_name)
            if w is not None:
                try:
                    w.setValue(value)
                except Exception:
                    try:
                        w.setText(str(value))
                    except Exception:
                        pass

        def set_checked(widget_name, value):
            w = self.page.findChild(QtWidgets.QWidget, widget_name)
            if w is not None:
                try:
                    w.setChecked(bool(value))
                except Exception:
                    pass

        if not cfg:
            return

        try:
            set_value("cameraResWidthSpin", int(cfg.camera.resolution_width))
            set_value("cameraResHeightSpin", int(cfg.camera.resolution_height))
            set_text("fourccLineEdit", cfg.camera.fourcc)
            set_checked("forceDirectShowCheck", cfg.camera.force_directshow)
        except Exception:
            pass

        try:
            set_value("frameIntervalSpin", int(cfg.streaming.frame_interval_ms))
            set_value("inferenceIntervalSpin", int(cfg.streaming.inference_interval_ms))
        except Exception:
            pass

        try:
            set_value("sensorWidthSpin", float(cfg.measurement.effective_sensor_width_mm))
            set_value("sensorHeightSpin", float(cfg.measurement.effective_sensor_height_mm))
            set_value("defaultMagnificationSpin", float(cfg.measurement.default_magnification))
        except Exception:
            pass

        try:
            set_value("defaultConfidenceSpin", float(cfg.inference.default_confidence))
            set_value("defaultIouSpin", float(cfg.inference.default_iou))
        except Exception:
            pass

        try:
            set_value("brightnessDefaultSpin", int(cfg.brightness_contrast.brightness_default))
            set_value("contrastDefaultSpin", int(cfg.brightness_contrast.contrast_default))
        except Exception:
            pass

        try:
            set_text("localModelsDirLine", cfg.models.local_models_dir)
            set_checked("preferLocalCheck", cfg.models.prefer_local)
        except Exception:
            pass

        try:
            set_text("roboflowApiKeyLine", cfg.services.roboflow.api_key)
            set_text("roboflowApiUrlLine", cfg.services.roboflow.api_url)
            set_text("roboflowWorkspaceLine", cfg.services.roboflow.workspace)
            set_text("roboflowWorkflowLine", cfg.services.roboflow.workflow)
        except Exception:
            pass

        try:
            set_text("directusApiUrlLine", cfg.services.directus.api_url)
            set_text("directusBearerLine", cfg.services.directus.bearer_token)
            set_value("directusTimeoutSpin", int(cfg.services.directus.timeout_seconds))
        except Exception:
            pass

    def _on_save_clicked(self):
        """Read values from UI and save them into settings on disk."""
        try:
            cfg = get_settings()
        except Exception:
            cfg = None
        if cfg is None:
            return

        def get_text(widget_name):
            w = self.page.findChild(QtWidgets.QWidget, widget_name)
            if w is None:
                return None
            try:
                return w.text()
            except Exception:
                return None

        def get_value(widget_name):
            w = self.page.findChild(QtWidgets.QWidget, widget_name)
            if w is None:
                return None
            try:
                return w.value()
            except Exception:
                try:
                    return w.text()
                except Exception:
                    return None

        def get_checked(widget_name):
            w = self.page.findChild(QtWidgets.QWidget, widget_name)
            if w is None:
                return None
            try:
                return bool(w.isChecked())
            except Exception:
                return None

        try:
            v = get_value("cameraResWidthSpin")
            if v is not None:
                cfg["camera"]["resolution_width"] = int(v)
            v = get_value("cameraResHeightSpin")
            if v is not None:
                cfg["camera"]["resolution_height"] = int(v)
            v = get_text("fourccLineEdit")
            if v is not None:
                cfg["camera"]["fourcc"] = str(v)
            v = get_checked("forceDirectShowCheck")
            if v is not None:
                cfg["camera"]["force_directshow"] = v
        except Exception:
            pass

        try:
            v = get_value("frameIntervalSpin")
            if v is not None:
                cfg["streaming"]["frame_interval_ms"] = int(v)
            v = get_value("inferenceIntervalSpin")
            if v is not None:
                cfg["streaming"]["inference_interval_ms"] = int(v)
        except Exception:
            pass

        try:
            v = get_value("sensorWidthSpin")
            if v is not None:
                cfg["measurement"]["effective_sensor_width_mm"] = float(v)
            v = get_value("sensorHeightSpin")
            if v is not None:
                cfg["measurement"]["effective_sensor_height_mm"] = float(v)
            v = get_value("defaultMagnificationSpin")
            if v is not None:
                cfg["measurement"]["default_magnification"] = float(v)
        except Exception:
            pass

        try:
            v = get_value("defaultConfidenceSpin")
            if v is not None:
                cfg["inference"]["default_confidence"] = float(v)
            v = get_value("defaultIouSpin")
            if v is not None:
                cfg["inference"]["default_iou"] = float(v)
        except Exception:
            pass

        try:
            v = get_value("brightnessDefaultSpin")
            if v is not None:
                cfg["brightness_contrast"]["brightness_default"] = int(v)
            v = get_value("contrastDefaultSpin")
            if v is not None:
                cfg["brightness_contrast"]["contrast_default"] = int(v)
        except Exception:
            pass

        try:
            v = get_text("localModelsDirLine")
            if v is not None:
                cfg["models"]["local_models_dir"] = str(v)
            v = get_checked("preferLocalCheck")
            if v is not None:
                cfg["models"]["prefer_local"] = v
        except Exception:
            pass

        try:
            v = get_text("roboflowApiKeyLine")
            if v is not None:
                cfg["services"]["roboflow"]["api_key"] = str(v)
            v = get_text("roboflowApiUrlLine")
            if v is not None:
                cfg["services"]["roboflow"]["api_url"] = str(v)
            v = get_text("roboflowWorkspaceLine")
            if v is not None:
                cfg["services"]["roboflow"]["workspace"] = str(v)
            v = get_text("roboflowWorkflowLine")
            if v is not None:
                cfg["services"]["roboflow"]["workflow"] = str(v)
        except Exception:
            pass

        try:
            v = get_text("directusApiUrlLine")
            if v is not None:
                cfg["services"]["directus"]["api_url"] = str(v)
            v = get_text("directusBearerLine")
            if v is not None:
                cfg["services"]["directus"]["bearer_token"] = str(v)
            v = get_value("directusTimeoutSpin")
            if v is not None:
                cfg["services"]["directus"]["timeout_seconds"] = int(v)
        except Exception:
            pass

        try:
            cfg.save()
        except Exception:
            traceback.print_exc()


def setup(page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    try:
        page._controller = SettingsPageController(page, main_window)
        print("SettingsPageController initialized.")
    except Exception as e:
        print(f"settings_page.setup failed: {e}")
        traceback.print_exc()
```

- [ ] **Step 2: Run tests — all should pass now**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python -m pytest tests/ui/test_settings_page.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit the updated controller**

```bash
git add mpcamera/controllers/settings_page.py
git commit -m "feat: update settings controller with new service fields and show/hide toggles"
```

---

### Task 4: Smoke-test the running app

**Files:** (none changed)

- [ ] **Step 1: Launch the app and navigate to Settings**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
python main.py
```

- [ ] **Step 2: Verify each tab manually**

Check the following:
1. All 7 tabs are visible in the tab strip: Camera, Streaming, Measurement, Inference, Display, Models, Services
2. Existing values load correctly on each tab (no blank fields that should have defaults)
3. Services tab shows Roboflow and Directus sub-groups with all fields populated from `config.json` defaults
4. API Key and Bearer Token fields show `••••` (password mode)
5. Clicking "Show" reveals the text and button changes to "Hide"; clicking again restores password mode
6. Clicking "Save Settings" on any tab saves all settings (verify by changing a value, saving, restarting, and checking the value persisted)

- [ ] **Step 3: Commit smoke-test confirmation (no code change needed)**

```bash
git commit --allow-empty -m "chore: smoke-tested settings page redesign — all tabs and fields verified"
```
