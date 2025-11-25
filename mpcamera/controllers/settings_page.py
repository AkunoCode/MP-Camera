import os
import traceback
from PyQt6 import QtWidgets
from mpcamera.config import get_settings


class SettingsPageController:
    """Controller to manage the Settings page UI: load values from config and save them."""

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
        # Connect Save button
        try:
            btn = self.page.findChild(QtWidgets.QPushButton, "saveSettingsButton")
            if btn is not None:
                btn.clicked.connect(self._on_save_clicked)
        except Exception:
            pass

    def load_values(self):
        """Load values from settings into the UI widgets."""
        try:
            cfg = get_settings()
        except Exception:
            cfg = None

        def set_if(widget_name, value, setter="setValue"):
            try:
                w = self.page.findChild(QtWidgets.QWidget, widget_name)
                if w is None:
                    return
                if setter == "setText":
                    w.setText(str(value))
                elif setter == "setChecked":
                    w.setChecked(bool(value))
                else:
                    # default: setValue
                    try:
                        w.setValue(value)
                    except Exception:
                        # fallback for line edit
                        try:
                            w.setText(str(value))
                        except Exception:
                            pass
            except Exception:
                pass

        # Camera
        if cfg:
            try:
                set_if("cameraResWidthSpin", int(cfg.camera.resolution_width))
                set_if("cameraResHeightSpin", int(cfg.camera.resolution_height))
                set_if("fourccLineEdit", cfg.camera.fourcc, setter="setText")
                set_if(
                    "forceDirectShowCheck",
                    bool(cfg.camera.force_directshow),
                    setter="setChecked",
                )
            except Exception:
                pass

            # Streaming
            try:
                set_if("frameIntervalSpin", int(cfg.streaming.frame_interval_ms))
                set_if(
                    "inferenceIntervalSpin", int(cfg.streaming.inference_interval_ms)
                )
            except Exception:
                pass

            # Measurement
            try:
                set_if(
                    "sensorWidthSpin", float(cfg.measurement.effective_sensor_width_mm)
                )
                set_if(
                    "sensorHeightSpin",
                    float(cfg.measurement.effective_sensor_height_mm),
                )
                set_if(
                    "defaultMagnificationSpin",
                    float(cfg.measurement.default_magnification),
                )
            except Exception:
                pass

            # Inference
            try:
                set_if("defaultConfidenceSpin", float(cfg.inference.default_confidence))
                set_if("defaultIouSpin", float(cfg.inference.default_iou))
            except Exception:
                pass

            # Brightness/Contrast
            try:
                set_if(
                    "brightnessDefaultSpin",
                    int(cfg.brightness_contrast.brightness_default),
                )
                set_if(
                    "contrastDefaultSpin", int(cfg.brightness_contrast.contrast_default)
                )
            except Exception:
                pass

            # Models
            try:
                set_if(
                    "localModelsDirLine", cfg.models.local_models_dir, setter="setText"
                )
                set_if(
                    "preferLocalCheck",
                    bool(cfg.models.prefer_local),
                    setter="setChecked",
                )
            except Exception:
                pass

            # Services
            try:
                set_if(
                    "roboflowApiKeyLine",
                    cfg.services.roboflow.api_key,
                    setter="setText",
                )
                set_if(
                    "directusBearerLine",
                    cfg.services.directus.bearer_token,
                    setter="setText",
                )
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

        def get_if(widget_name, getter="value"):
            try:
                w = self.page.findChild(QtWidgets.QWidget, widget_name)
                if w is None:
                    return None
                if getter == "text":
                    return w.text()
                if getter == "checked":
                    return bool(w.isChecked())
                try:
                    return w.value()
                except Exception:
                    try:
                        return w.text()
                    except Exception:
                        return None
            except Exception:
                return None

        # Camera
        try:
            w = get_if("cameraResWidthSpin")
            if w is not None:
                cfg["camera"]["resolution_width"] = int(w)
            h = get_if("cameraResHeightSpin")
            if h is not None:
                cfg["camera"]["resolution_height"] = int(h)
            fourcc = get_if("fourccLineEdit", getter="text")
            if fourcc is not None:
                cfg["camera"]["fourcc"] = str(fourcc)
            fd = get_if("forceDirectShowCheck", getter="checked")
            if fd is not None:
                cfg["camera"]["force_directshow"] = bool(fd)
        except Exception:
            pass

        # Streaming
        try:
            fi = get_if("frameIntervalSpin")
            if fi is not None:
                cfg["streaming"]["frame_interval_ms"] = int(fi)
            ii = get_if("inferenceIntervalSpin")
            if ii is not None:
                cfg["streaming"]["inference_interval_ms"] = int(ii)
        except Exception:
            pass

        # Measurement
        try:
            sw = get_if("sensorWidthSpin")
            if sw is not None:
                cfg["measurement"]["effective_sensor_width_mm"] = float(sw)
            sh = get_if("sensorHeightSpin")
            if sh is not None:
                cfg["measurement"]["effective_sensor_height_mm"] = float(sh)
            mag = get_if("defaultMagnificationSpin")
            if mag is not None:
                cfg["measurement"]["default_magnification"] = float(mag)
        except Exception:
            pass

        # Inference
        try:
            dc = get_if("defaultConfidenceSpin")
            if dc is not None:
                cfg["inference"]["default_confidence"] = float(dc)
            di = get_if("defaultIouSpin")
            if di is not None:
                cfg["inference"]["default_iou"] = float(di)
        except Exception:
            pass

        # Brightness/Contrast
        try:
            bd = get_if("brightnessDefaultSpin")
            if bd is not None:
                cfg["brightness_contrast"]["brightness_default"] = int(bd)
            cd = get_if("contrastDefaultSpin")
            if cd is not None:
                cfg["brightness_contrast"]["contrast_default"] = int(cd)
        except Exception:
            pass

        # Models
        try:
            lm = get_if("localModelsDirLine", getter="text")
            if lm is not None:
                cfg["models"]["local_models_dir"] = str(lm)
            pl = get_if("preferLocalCheck", getter="checked")
            if pl is not None:
                cfg["models"]["prefer_local"] = bool(pl)
        except Exception:
            pass

        # Services
        try:
            rf = get_if("roboflowApiKeyLine", getter="text")
            if rf is not None:
                cfg["services"]["roboflow"]["api_key"] = str(rf)
            dr = get_if("directusBearerLine", getter="text")
            if dr is not None:
                cfg["services"]["directus"]["bearer_token"] = str(dr)
        except Exception:
            pass

        # Save settings (Settings.save handles path)
        try:
            cfg.save()
        except Exception:
            try:
                # fallback: try function if available
                from mpcamera.config import save_settings

                save_settings(cfg)
            except Exception:
                traceback.print_exc()


def setup(page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    try:
        page._controller = SettingsPageController(page, main_window)
        print("SettingsPageController initialized.")
    except Exception as e:
        print(f"settings_page.setup failed: {e}")
        traceback.print_exc()
