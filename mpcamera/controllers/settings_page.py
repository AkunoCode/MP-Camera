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
            self._validate_and_warn()
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

    def _validate_and_warn(self):
        """Check for missing critical API keys and warn user."""
        try:
            cfg = get_settings()
        except Exception:
            return

        missing = []

        # Check Roboflow API key
        try:
            rf_key = cfg.services.roboflow.api_key
            if not rf_key or not str(rf_key).strip():
                missing.append("Roboflow API Key")
        except Exception:
            missing.append("Roboflow API Key")

        # Check Directus Bearer Token
        try:
            du_token = cfg.services.directus.bearer_token
            if not du_token or not str(du_token).strip():
                missing.append("Directus Bearer Token")
        except Exception:
            missing.append("Directus Bearer Token")

        if missing:
            msg = f"⚠️  Missing required API credentials:\n\n" + "\n".join(f"  • {item}" for item in missing) + \
                  "\n\nPlease configure these in the Services tab before using inference features."
            try:
                QtWidgets.QMessageBox.warning(self.page, "Missing API Credentials", msg)
            except Exception:
                print(msg)

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
