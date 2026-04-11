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
