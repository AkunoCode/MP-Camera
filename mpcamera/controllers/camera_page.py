import cv2
import json
import os
import glob
import tempfile
import traceback
import threading
import numpy as np
from pathlib import Path
from threading import Thread
from typing import Optional, List, Dict, Any
from enum import Enum, auto

from PyQt6 import QtWidgets, QtCore, QtGui
from mpcamera.config import get_settings

# --- CAMERA DETECTION IMPORT ---
from PyQt6.QtMultimedia import QMediaDevices

# --- Safe Service Imports ---
try:
    from mpcamera.services.roboflow import RoboflowClient
except ImportError:
    RoboflowClient = None
try:
    from mpcamera.services.directus import DirectusClient
except ImportError:
    DirectusClient = None

# --- Utils & UI Imports ---
from mpcamera.utils.results_manager import ResultsManager
from mpcamera.utils.camera_worker import CameraWorker

try:
    from mpcamera.utils.inference_worker import InferenceWorker
except Exception:
    InferenceWorker = None
try:
    from mpcamera.utils.form_handler import FormHandler
except Exception:
    FormHandler = None
try:
    from mpcamera.ui.results_window import ResultsWindow
except Exception:
    ResultsWindow = None
from mpcamera.utils.camera_utils import extract_directus_items, get_site_id_from_sample
from mpcamera.utils.prediction_utils import extract_points_from_prediction
from mpcamera.ui.overlays import ensure_overlay_for_view, render_predictions_on_scene
from mpcamera.utils.inference_utils import (
    parse_result_to_preds,
    compute_aggregates,
    apply_confidence_iou_filters,
)
from mpcamera.utils.um_per_pixel import calculate_micrometers_per_pixel
from mpcamera.utils.color_utils import get_color_name
from mpcamera.utils.morphometrics import (
    calculate_area_um2,
    calculate_perimeter_um,
    calculate_major_axis_um,
    calculate_minor_axis_um,
    calculate_equivalent_circular_diameter,
    calculate_skeleton_length_um,
)

# Image adjustment util
try:
    from mpcamera.utils.image_utils import adjust_brightness_contrast
except Exception:
    adjust_brightness_contrast = None

# Import the local inference class
try:
    from mpcamera.utils.local_models_utils import LocalModelInference
except ImportError:
    LocalModelInference = None


class CameraState(Enum):
    """State machine for camera page operations."""
    IDLE = auto()
    STREAMING = auto()
    PAUSED = auto()
    INFERRING = auto()


class CameraPageController(QtCore.QObject):
    """
    Controller to manage the logic, state, and UI interactions of the Camera Page.
    Includes robust error handling and logging for data population.
    """

    # Signals
    inference_finished_signal = QtCore.pyqtSignal(object, str)  # result, temp_path
    data_saved_signal = QtCore.pyqtSignal(int)  # count of saved items

    # Constants
    FRAME_INTERVAL_MS = 33  # ~30 FPS
    INFERENCE_INTERVAL_MS = 1000

    # Default Defaults (Overridden by sliders if present)
    DEFAULT_CONFIDENCE = 0.40
    DEFAULT_IOU = 0.50

    DEFAULT_MODEL = ("YOLOv11 (Cloud)", "detect-count-and-visualize-2")
    ALT_MODEL = ("RF-DETR-SEG (Cloud)", "detect-count-and-visualize")

    # Local Model Configuration
    LOCAL_MODELS_DIR = os.path.join(os.getcwd(), "models")
    LOCAL_NUM_CLASSES = 6
    CLASS_MAP = {
        0: "Background",
        1: "Fragment",
        2: "Pellet",
        3: "Fiber",
        4: "Sheet",
        5: "Foam",
    }

    def __init__(
        self, camera_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow
    ):
        super().__init__()
        self.page = camera_page
        self.main_window = main_window

        # --- State ---
        self._vc: Optional[cv2.VideoCapture] = None
        self._streaming = False
        self._paused = False
        self._inference_running = False
        self._last_pixmap: Optional[QtGui.QPixmap] = None
        self._current_frame_np: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()  # Synchronize access to frame buffers
        self._camera_state = CameraState.IDLE
        self._cached_soils: List[Dict] = []
        # Currently selected camera device index (int). Defaults to 0.
        self._selected_camera_index: int = 0
        self._prefer_local_model: bool = False

        # Local Inference State
        self._local_engine = None
        self._current_local_model_path = None
        # Large inference window (separate view for full table)
        self._large_table_window: Optional[QtWidgets.QMainWindow] = None
        # Last parsed predictions (for viewDetails button)
        self._last_preds: List[Dict[str, Any]] = []
        self._last_raw_result = None  # unfiltered inference output for slider re-use

        # --- Timers ---
        self._frame_timer = QtCore.QTimer()
        self._frame_timer.setInterval(self.FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_frame_tick)

        self._stream_inference_timer = QtCore.QTimer()
        self._stream_inference_timer.setInterval(self.INFERENCE_INTERVAL_MS)
        self._stream_inference_timer.timeout.connect(self._maybe_run_stream_inference)

        # Override class/static defaults with user settings when available
        try:
            cfg = get_settings()
            # Timers
            try:
                self._frame_timer.setInterval(int(cfg.streaming.frame_interval_ms))
            except Exception:
                pass
            try:
                self._stream_inference_timer.setInterval(
                    int(cfg.streaming.inference_interval_ms)
                )
            except Exception:
                pass

            # Inference defaults
            try:
                self.DEFAULT_CONFIDENCE = float(cfg.inference.default_confidence)
            except Exception:
                pass
            try:
                self.DEFAULT_IOU = float(cfg.inference.default_iou)
            except Exception:
                pass

            # Model defaults and local models dir
            try:
                dm = cfg.models.default_model
                # expected shape from schema: {display_name, workflow_id}
                self.DEFAULT_MODEL = (
                    str(dm.get("display_name", "")),
                    str(dm.get("workflow_id", "")),
                )
            except Exception:
                pass
            try:
                self.LOCAL_MODELS_DIR = self._resolve_local_models_dir(
                    str(cfg.models.local_models_dir)
                )
            except Exception:
                self.LOCAL_MODELS_DIR = self._resolve_local_models_dir(
                    self.LOCAL_MODELS_DIR
                )
            try:
                self._prefer_local_model = bool(cfg.models.prefer_local)
            except Exception:
                self._prefer_local_model = False

            # Brightness / contrast defaults
            try:
                self._brightness_default = int(
                    cfg.brightness_contrast.brightness_default
                )
            except Exception:
                self._brightness_default = 50
            try:
                self._contrast_default = int(cfg.brightness_contrast.contrast_default)
            except Exception:
                self._contrast_default = 50
        except Exception:
            # no settings available; keep class defaults
            self._brightness_default = 50
            self._contrast_default = 50
            self.LOCAL_MODELS_DIR = self._resolve_local_models_dir(self.LOCAL_MODELS_DIR)

        # --- Init Sequence ---
        self.ui = self._find_ui_elements()
        # Overlay visibility state (default ON)
        self._overlays_visible = True
        self._replace_graphics_view()
        self._init_ui_defaults()
        self._setup_connections()

        # Camera worker (reads frames on its own timer and emits numpy frames)
        try:
            self._camera_worker = CameraWorker()
            self._camera_worker.frame_received.connect(self._on_worker_frame)
            self._camera_worker.error_occurred.connect(self._on_worker_error)
        except Exception:
            self._camera_worker = None

        # Inference worker (runs local or cloud inference in background)
        try:
            self._inference_worker = InferenceWorker()
            self._inference_worker.finished.connect(self._on_inference_worker_finished)
            self._inference_worker.error.connect(self._on_inference_worker_error)
        except Exception:
            self._inference_worker = None

        # Form handler to manage farm/soil combos
        try:
            self._form_handler = FormHandler(
                self.ui.get("farm_combo"), self.ui.get("soil_combo")
            )
        except Exception:
            self._form_handler = None

        # --- Data Loading ---
        # Initial load attempt
        self._populate_data()

        # Listen for future data updates from MainWindow
        if hasattr(main_window, "dataLoaded"):
            try:
                main_window.dataLoaded.disconnect(self._populate_data)
            except Exception:
                pass
            main_window.dataLoaded.connect(self._populate_data)

    def _resolve_local_models_dir(self, configured_dir: Optional[str]) -> str:
        """Resolve the local models directory with safe fallbacks.

        Priority:
        1) Configured path (absolute)
        2) Configured path relative to project root
        3) Configured path relative to current working directory
        4) Project root /models
        5) Project root /mpcamera/models (legacy)
        """
        try:
            project_root = Path(__file__).resolve().parents[2]
        except Exception:
            project_root = Path.cwd()

        candidates: List[Path] = []
        if configured_dir:
            try:
                cfg_path = Path(str(configured_dir)).expanduser()
                if cfg_path.is_absolute():
                    candidates.append(cfg_path)
                else:
                    candidates.append(project_root / cfg_path)
                    candidates.append(Path.cwd() / cfg_path)
            except Exception:
                pass

        candidates.append(project_root / "models")
        candidates.append(project_root / "mpcamera" / "models")

        seen = set()
        for candidate in candidates:
            try:
                norm = str(candidate.resolve())
            except Exception:
                norm = str(candidate)
            if norm in seen:
                continue
            seen.add(norm)
            if os.path.isdir(norm):
                return norm

        # No existing dir yet: return best intended target for future files
        if configured_dir:
            try:
                cfg_path = Path(str(configured_dir)).expanduser()
                if cfg_path.is_absolute():
                    return str(cfg_path)
                return str((project_root / cfg_path).resolve())
            except Exception:
                pass
        return str((project_root / "models").resolve())

    def _set_state(self, new_state: CameraState):
        """Atomically transition to new_state and sync legacy flags."""
        old = self._camera_state
        self._camera_state = new_state

        # Sync legacy boolean flags so existing code stays correct
        self._streaming = new_state in (CameraState.STREAMING, CameraState.INFERRING)
        self._paused = new_state == CameraState.PAUSED
        self._inference_running = new_state == CameraState.INFERRING

        print(f"[STATE] {old.name} → {new_state.name}")

    def _find_ui_elements(self) -> Dict[str, Any]:
        """Locate and cache UI widgets. Returns a dict to avoid attribute clutter."""
        elements = {
            "farm_combo": self.page.findChild(QtWidgets.QComboBox, "farmCombo"),
            "soil_combo": self.page.findChild(QtWidgets.QComboBox, "soilCombo"),
            "model_combo": self.page.findChild(QtWidgets.QComboBox, "modelCombo"),
            "cam_view": self.page.findChild(QtWidgets.QGraphicsView, "cameraView"),
            "inf_table": self.page.findChild(QtWidgets.QTableWidget, "inferenceTable"),
            "img_btn": self.page.findChild(QtWidgets.QPushButton, "imgUploadButton"),
            "cam_btn": self.page.findChild(
                QtWidgets.QPushButton, "cameraControlButton"
            ),
            "cap_btn": self.page.findChild(QtWidgets.QPushButton, "captureButton"),
            "clear_btn": self.page.findChild(QtWidgets.QPushButton, "clearImgButton"),
            "save_btn": self.page.findChild(QtWidgets.QPushButton, "saveResultButton"),
            "mag_spin": self.page.findChild(
                QtWidgets.QDoubleSpinBox, "magnificationSpinbox"
            ),
            "source_combo": self.page.findChild(QtWidgets.QComboBox, "sourceCombo"),
            "reload_btn": self.page.findChild(QtWidgets.QPushButton, "reloadButton"),
            "view_btn": self.page.findChild(QtWidgets.QPushButton, "viewButton"),
            # viewDetails button (replaces the inline inference table in some UI versions)
            "view_details_btn": self.page.findChild(
                QtWidgets.QPushButton, "viewDetails"
            ),
            # sliders for brightness / contrast
            "brightness_slider": self.page.findChild(
                QtWidgets.QSlider, "brightnessSlider"
            ),
            "contrast_slider": self.page.findChild(QtWidgets.QSlider, "contrastSlider"),
            # Sliders
            "conf_slider": self.page.findChild(QtWidgets.QSlider, "confidenceSlider"),
            "iou_slider": self.page.findChild(QtWidgets.QSlider, "iouSlider"),
            # Labels for sliders
            "confidence": self.page.findChild(QtWidgets.QLabel, "confidence"),
            "iou": self.page.findChild(QtWidgets.QLabel, "iou"),
            # Stats Labels
            "lbl_total": self.page.findChild(QtWidgets.QLabel, "totalCount"),
            "lbl_conf": self.page.findChild(QtWidgets.QLabel, "aveConfidence"),
            "lbl_frag": self.page.findChild(QtWidgets.QLabel, "fragmentsCount"),
            "lbl_sheet": self.page.findChild(QtWidgets.QLabel, "sheetsCount"),
            "lbl_fiber": self.page.findChild(QtWidgets.QLabel, "fibersCount"),
            "lbl_foam": self.page.findChild(QtWidgets.QLabel, "foamsCount"),
            "lbl_film": self.page.findChild(QtWidgets.QLabel, "filmsCount"),
            "lbl_bead": self.page.findChild(QtWidgets.QLabel, "beadsCount"),
        }

        # Debug logs for missing elements (Critical for troubleshooting UI load issues)
        missing = [k for k, v in elements.items() if v is None]
        # If a dedicated viewDetails button wasn't found by objectName, try a best-effort search
        if elements.get("view_details_btn") is None:
            try:
                for btn in self.page.findChildren(QtWidgets.QPushButton):
                    try:
                        obj = (btn.objectName() or "").lower()
                        txt = (btn.text() or "").lower()
                        if ("view" in obj and "detail" in obj) or (
                            "view" in txt and "detail" in txt
                        ):
                            elements["view_details_btn"] = btn
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        missing = [k for k, v in elements.items() if v is None]
        if missing:
            print(f"[CAMERA PAGE] Warning: UI elements not found: {missing}")

        return elements

    def _setup_connections(self):
        """Wire signals to slots using explicit None checks."""
        ui = self.ui

        # Dropdowns
        if ui["farm_combo"] is not None:
            ui["farm_combo"].currentIndexChanged.connect(self._on_farm_changed)
        if ui["soil_combo"] is not None:
            ui["soil_combo"].currentIndexChanged.connect(self._on_soil_changed)
        if ui["model_combo"] is not None:
            ui["model_combo"].currentIndexChanged.connect(self._on_model_changed)
        # Camera source combobox
        if ui.get("source_combo") is not None:
            ui["source_combo"].currentIndexChanged.connect(self._on_source_changed)

        # Buttons
        if ui["cam_btn"] is not None:
            ui["cam_btn"].clicked.connect(self._toggle_camera)
        if ui.get("reload_btn") is not None:
            ui["reload_btn"].clicked.connect(self._on_reload_clicked)
        if ui.get("view_btn") is not None:
            ui["view_btn"].clicked.connect(self._on_view_toggled)
        # If a dedicated 'view details' button exists, open the large table on click
        if ui.get("view_details_btn") is not None:
            ui["view_details_btn"].clicked.connect(self._on_view_details_clicked)
        if ui["cap_btn"] is not None:
            ui["cap_btn"].clicked.connect(self._toggle_capture)
        if ui["clear_btn"] is not None:
            ui["clear_btn"].clicked.connect(self._clear_all)
        if ui["img_btn"] is not None:
            ui["img_btn"].clicked.connect(self._upload_image)
        if ui["save_btn"] is not None:
            ui["save_btn"].clicked.connect(self._save_results)

        # Sliders - Use sliderReleased to re-filter from cache (no new inference)
        if ui["conf_slider"] is not None:
            ui["conf_slider"].sliderReleased.connect(self._refilter_from_cache)
            # Update label live as the slider moves
            ui["conf_slider"].valueChanged.connect(self._update_param_labels)
        if ui["iou_slider"] is not None:
            ui["iou_slider"].sliderReleased.connect(self._refilter_from_cache)
            ui["iou_slider"].valueChanged.connect(self._update_param_labels)
        # Note: brightness/contrast sliders are initialized in _init_ui_defaults
        # so that their values are applied before the first _apply_adjustments_and_refresh call.

        # Worker signals
        self.data_saved_signal.connect(self._on_save_finished)

        # Table interaction
        if ui["inf_table"] is not None:
            ui["inf_table"].selectionModel().selectionChanged.connect(
                self._on_table_selection
            )

    def _init_ui_defaults(self):
        """Populate static UI elements and defaults."""
        hand_cursor = QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        for widget in self.ui.values():
            if widget is not None and isinstance(
                widget,
                (
                    QtWidgets.QPushButton,
                    QtWidgets.QComboBox,
                    QtWidgets.QTableWidget,
                    QtWidgets.QSlider,
                ),
            ):
                widget.setCursor(hand_cursor)

        # Init Sliders (Range 0-100 for percentage)
        if self.ui["conf_slider"] is not None:
            self.ui["conf_slider"].setRange(0, 100)
            self.ui["conf_slider"].setValue(int(self.DEFAULT_CONFIDENCE * 100))

        if self.ui["iou_slider"] is not None:
            self.ui["iou_slider"].setRange(0, 100)
            self.ui["iou_slider"].setValue(int(self.DEFAULT_IOU * 100))

        # Update the slider labels to show percentage values
        try:
            self._update_param_labels()
        except Exception:
            pass

        # Ensure any brightness/contrast defaults are applied to current image
        try:
            self._apply_adjustments_and_refresh()
        except Exception:
            pass

        # Initialize Brightness/Contrast sliders so adjustments apply immediately
        try:
            b_slider = self.ui.get("brightness_slider")
            c_slider = self.ui.get("contrast_slider")
            if b_slider is not None:
                b_slider.setRange(0, 100)
                try:
                    b_slider.setValue(int(self._brightness_default))
                except Exception:
                    b_slider.setValue(50)
                b_slider.valueChanged.connect(self._on_brightness_contrast_changed)
                try:
                    b_slider.sliderReleased.connect(
                        self._on_brightness_contrast_released
                    )
                except Exception:
                    pass
            if c_slider is not None:
                c_slider.setRange(0, 100)
                try:
                    c_slider.setValue(int(self._contrast_default))
                except Exception:
                    c_slider.setValue(50)
                c_slider.valueChanged.connect(self._on_brightness_contrast_changed)
                try:
                    c_slider.sliderReleased.connect(
                        self._on_brightness_contrast_released
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # Init Model Combo
        combo = self.ui["model_combo"]
        if combo is not None:
            combo.blockSignals(True)
            combo.clear()

            # 1. Add Cloud Models
            combo.addItem(*self.DEFAULT_MODEL)
            combo.addItem(*self.ALT_MODEL)

            # 2. Add Local Models
            self._populate_local_models(combo)

            selected_local = False
            if self._prefer_local_model:
                try:
                    for i in range(combo.count()):
                        data = combo.itemData(i)
                        if isinstance(data, str) and data.lower().endswith((".pth", ".pt")):
                            combo.setCurrentIndex(i)
                            selected_local = True
                            self._current_local_model_path = data
                            break
                except Exception:
                    selected_local = False

            # Sync with current Roboflow default if available
            if RoboflowClient and not selected_local:
                try:
                    current_wf = RoboflowClient.get_default().workflow
                    idx = combo.findData(current_wf)
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                except Exception:
                    combo.setCurrentIndex(0)
            combo.blockSignals(False)

        # Populate camera source combo (detect available cameras)
        try:
            self._populate_source_combo()
        except Exception:
            pass

        # Initialize magnification control from settings when present
        try:
            mag = self.ui.get("mag_spin")
            if mag is not None:
                try:
                    cfg = get_settings()
                    mag_val = float(cfg.measurement.default_magnification)
                    mag.setValue(mag_val)
                except Exception:
                    # leave widget default
                    pass
                try:
                    mag.editingFinished.connect(self._on_magnification_changed)
                except Exception:
                    pass
        except Exception:
            pass

    def _populate_local_models(self, combo: QtWidgets.QComboBox):
        """Scans the models directory and adds local model files (.pth and .pt) to the combobox."""
        if not os.path.exists(self.LOCAL_MODELS_DIR):
            print(f"[CAMERA PAGE] Models directory not found: {self.LOCAL_MODELS_DIR}")
            hint_text = "Local: No models folder found"
            combo.insertSeparator(combo.count())
            combo.addItem(hint_text, None)
            try:
                idx = combo.findText(hint_text)
                if idx >= 0 and combo.model() is not None:
                    item = combo.model().item(idx)
                    if item is not None:
                        item.setEnabled(False)
            except Exception:
                pass
            return
        # Include both .pth (PyTorch) and .pt (Ultralytics / other) weights
        pth_files = glob.glob(os.path.join(self.LOCAL_MODELS_DIR, "*.pth"))
        pt_files = glob.glob(os.path.join(self.LOCAL_MODELS_DIR, "*.pt"))
        model_files = sorted(list(set(pth_files + pt_files)))
        if not model_files:
            print(f"[CAMERA PAGE] No .pt/.pth files found in {self.LOCAL_MODELS_DIR}")
            hint_text = "Local: No .pt/.pth files found"
            combo.insertSeparator(combo.count())
            combo.addItem(hint_text, None)
            try:
                idx = combo.findText(hint_text)
                if idx >= 0 and combo.model() is not None:
                    item = combo.model().item(idx)
                    if item is not None:
                        item.setEnabled(False)
            except Exception:
                pass
            return

        print(f"[CAMERA PAGE] Found {len(model_files)} local models.")
        combo.insertSeparator(combo.count())

        for p in model_files:
            filename = os.path.basename(p)
            # Display name matches filename, Data is the full path
            combo.addItem(f"Local: {filename}", p)

    def _replace_graphics_view(self):
        """Swap standard QGraphicsView with ZoomableGraphicsView at runtime."""
        old_view = self.ui["cam_view"]
        if old_view is None:
            return

        try:
            from mpcamera.ui.zoomable_view import ZoomableGraphicsView

            if isinstance(old_view, ZoomableGraphicsView):
                return

            parent = old_view.parentWidget()
            new_view = ZoomableGraphicsView(parent)

            # Copy properties
            new_view.setObjectName(old_view.objectName())
            new_view.setSizePolicy(old_view.sizePolicy())
            new_view.setMinimumSize(old_view.minimumSize())
            new_view.setMaximumSize(old_view.maximumSize())

            # Swap in layout
            layout = parent.layout() if parent else None
            if layout:
                layout.replaceWidget(old_view, new_view)

            old_view.setParent(None)
            self.ui["cam_view"] = new_view

            # Enable tracking
            new_view.setMouseTracking(True)
            if new_view.viewport():
                new_view.viewport().setMouseTracking(True)
                try:
                    # Ensure the viewport background defaults to black so
                    # images/videos have a black letterbox/pad behind them.
                    new_view.viewport().setStyleSheet("background-color: black;")
                except Exception:
                    pass

        except ImportError:
            print("ZoomableGraphicsView not found, using default.")
        except Exception as e:
            print(f"View replacement failed: {e}")

    # ================= DATA LOADING =================

    def _populate_data(self):
        """
        Fetches Sites/Soils and populates dropdowns.
        Includes specific fixes: Re-acquires UI refs, explicit None checks, and debug logging.
        """
        try:
            print(
                f"[CAMERA PAGE] _populate_data running in thread={threading.current_thread().name}"
            )

            # 1. Re-acquire UI elements in case UI was reloaded
            self.ui = self._find_ui_elements()

            # 2. Defensive getters
            get_sites = getattr(self.main_window, "get_sites", lambda: [])
            get_soils = getattr(self.main_window, "get_soilsamples", lambda: [])

            sites = extract_directus_items(get_sites())
            soils = extract_directus_items(get_soils())

            # 3. Debug Logging
            print(
                f"[CAMERA PAGE] fetched sites count={len(sites) if sites is not None else 0}"
            )
            print(
                f"[CAMERA PAGE] fetched soils count={len(soils) if soils is not None else 0}"
            )

            # 4. Update Cache & Backwards Compat
            self._cached_soils = soils or []
            setattr(self.main_window, "_camera_sites_list", sites)
            setattr(self.main_window, "_camera_soils_list", self._cached_soils)

            # 5. Update Farm Combo
            self._update_farm_combo(sites)

            # 6. Update Soil Combo (based on current selection)
            current_farm_id = None
            if self.ui["farm_combo"] is not None:
                current_farm_id = self.ui["farm_combo"].currentData()

            print(f"[CAMERA PAGE] initial filter soil by farm_id={current_farm_id}")
            self._filter_soil_combo(current_farm_id)

        except Exception as e:
            print(f"CameraPageController: Data population error: {e}")
            traceback.print_exc()

    def _update_farm_combo(self, sites: List[Dict]):
        combo = self.ui["farm_combo"]

        if combo is None:
            return

        if not sites:
            print("[CAMERA PAGE] update_farm_combo: No sites to add.")
            return

        combo.blockSignals(True)
        combo.clear()

        for idx, item in enumerate(sites):
            try:
                name = item.get("site_name") or item.get("name") or str(item.get("id"))
                combo.addItem(str(name), item.get("id"))
            except Exception as e:
                print(f"[CAMERA PAGE] failed to add farm item idx={idx} error={e}")

        combo.setCurrentIndex(-1)
        combo.blockSignals(False)

    def _filter_soil_combo(self, site_id):
        combo = self.ui["soil_combo"]

        if combo is None:
            return

        combo.blockSignals(True)
        combo.clear()

        count = 0
        for item in self._cached_soils:
            s_site = get_site_id_from_sample(item)
            # Show if site_id is None (show all) OR matches
            if site_id is None or site_id == s_site:
                try:
                    sid = item.get("id")
                    date = item.get("date_collected") or item.get("date") or ""
                    label = f"Sample ID {sid} ({date})"
                    combo.addItem(label, sid)
                    count += 1
                except Exception as e:
                    print(f"[CAMERA PAGE] failed to add soil item error={e}")

        combo.blockSignals(False)

    # ================= EVENT HANDLERS =================

    def _on_farm_changed(self):
        if self.ui["farm_combo"] is None:
            return
        site_id = self.ui["farm_combo"].currentData()
        self._filter_soil_combo(site_id)

    def _on_soil_changed(self):
        # Auto-select farm if a soil is selected
        if self.ui["soil_combo"] is None:
            return

        sid = self.ui["soil_combo"].currentData()
        if not sid:
            return

        match = next((i for i in self._cached_soils if i.get("id") == sid), None)
        if match and self.ui["farm_combo"] is not None:
            site_id = get_site_id_from_sample(match)
            if site_id:
                idx = self.ui["farm_combo"].findData(site_id)
                if idx != -1:
                    self.ui["farm_combo"].blockSignals(True)
                    self.ui["farm_combo"].setCurrentIndex(idx)
                    self.ui["farm_combo"].blockSignals(False)

    def _on_view_details_clicked(self):
        """Open the large inference table window showing the last inference results."""
        try:
            if self._last_preds:
                self._open_large_table_window(self._last_preds)
            else:
                QtWidgets.QMessageBox.information(
                    self.page, "No Results", "No inference results available."
                )
        except Exception as e:
            print(f"Failed opening large inference window from button: {e}")

    def _on_param_changed(self):
        """Called when Confidence or IoU slider is adjusted/released."""
        # Ensure labels reflect the final values
        try:
            self._update_param_labels()
        except Exception:
            pass

        print("[CAMERA PAGE] Model parameters changed, re-running inference...")
        if self._last_pixmap is not None:
            self._run_inference_on_pixmap(self._last_pixmap, is_temp=True)

    def _update_param_labels(self):
        """Refresh the text of the Confidence and IoU labels to include current percent value."""
        ui = self.ui
        try:
            conf_pct = (
                ui["conf_slider"].value()
                if ui.get("conf_slider") is not None
                else int(self.DEFAULT_CONFIDENCE * 100)
            )
            iou_pct = (
                ui["iou_slider"].value()
                if ui.get("iou_slider") is not None
                else int(self.DEFAULT_IOU * 100)
            )

            if ui.get("confidence") is not None:
                ui["confidence"].setText(f"Confidence ({int(conf_pct)}%)")
            if ui.get("iou") is not None:
                ui["iou"].setText(f"IoU ({int(iou_pct)}%)")
        except Exception:
            pass

    def _on_brightness_contrast_changed(self, _val=None):
        """Handler when brightness/contrast sliders change; refresh displayed frame."""
        try:
            self._apply_adjustments_and_refresh()
        except Exception:
            pass

    def _on_brightness_contrast_released(self):
        """Called when user finishes adjusting brightness/contrast; persist defaults."""
        try:
            self._save_ui_settings()
        except Exception:
            pass

    def _on_magnification_changed(self):
        """Persist magnification when editing finished."""
        try:
            self._save_ui_settings()
        except Exception:
            pass

    def _save_ui_settings(self):
        """Persist current UI defaults (brightness, contrast, magnification) to user config."""
        try:
            settings = get_settings()
            # Ensure nested structures exist
            if not hasattr(settings, "brightness_contrast"):
                settings["brightness_contrast"] = {}
            if not hasattr(settings, "measurement"):
                settings["measurement"] = {}

            b = None
            c = None
            mag = None

            try:
                b_widget = self.ui.get("brightness_slider")
                if b_widget is not None:
                    b = int(b_widget.value())
            except Exception:
                b = None
            try:
                c_widget = self.ui.get("contrast_slider")
                if c_widget is not None:
                    c = int(c_widget.value())
            except Exception:
                c = None
            try:
                mag_widget = self.ui.get("mag_spin")
                if mag_widget is not None:
                    mag = float(mag_widget.value())
            except Exception:
                mag = None

            if b is not None:
                settings["brightness_contrast"]["brightness_default"] = b
                self._brightness_default = b
            if c is not None:
                settings["brightness_contrast"]["contrast_default"] = c
                self._contrast_default = c
            if mag is not None:
                settings["measurement"]["default_magnification"] = mag

            # Persist to disk
            try:
                settings.save()
            except Exception:
                # Best-effort: ignore save failures
                pass
        except Exception:
            pass

    def _apply_adjustments_and_refresh(self):
        """Apply brightness/contrast to the latest raw frame (if any) and update display/pixmap.

        This ensures both what the user sees and the image sent to inference use the adjusted image.
        """
        if adjust_brightness_contrast is None:
            return

        # Safely read frame buffer under lock
        with self._frame_lock:
            raw = getattr(self, "_raw_frame_np", None)
            if raw is None:
                raw = self._current_frame_np
            if raw is not None:
                raw = raw.copy()  # Work on a snapshot outside the lock

        if raw is None:
            return

        # Read slider values (0-100)
        b_val = (
            self.ui.get("brightness_slider").value()
            if self.ui.get("brightness_slider") is not None
            else 50
        )
        c_val = (
            self.ui.get("contrast_slider").value()
            if self.ui.get("contrast_slider") is not None
            else 50
        )

        try:
            adjusted = adjust_brightness_contrast(
                raw, brightness_pct=b_val, contrast_pct=c_val
            )
        except Exception:
            adjusted = raw

        # Convert once for display; store BGR separately for inference/color analysis
        try:
            frame_rgb = cv2.cvtColor(adjusted, cv2.COLOR_BGR2RGB)
            with self._frame_lock:
                self._current_frame_np = adjusted  # keep BGR for downstream (color analysis uses BGR)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            qimg = QtGui.QImage(
                frame_rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888
            )
            self._last_pixmap = QtGui.QPixmap.fromImage(qimg.copy())
            self._display_pixmap(self._last_pixmap)
        except Exception:
            pass

    def _on_model_changed(self):
        """Update config or local state when model changes."""
        if self.ui["model_combo"] is None:
            return

        idx = self.ui["model_combo"].currentIndex()
        data = self.ui["model_combo"].itemData(idx)

        # Check if it is a local file path
        if isinstance(data, str) and data.lower().endswith((".pth", ".pt")):
            print(f"[CAMERA PAGE] Selected local model: {data}")
            # If we switch models, we might want to reset the engine so it reloads
            if self._current_local_model_path != data:
                self._local_engine = None
                self._current_local_model_path = data
        elif RoboflowClient and data:
            # It's a Roboflow ID
            try:
                RoboflowClient.get_default().workflow = data
                print(f"[CAMERA PAGE] Roboflow workflow set to {data}")
                # Reset local state
                self._current_local_model_path = None
                self._local_engine = None
            except Exception:
                pass

        # Re-run inference if static image exists
        if self._last_pixmap is not None:
            print(f"[CAMERA PAGE] re-running inference due to model change")
            self._run_inference_on_pixmap(self._last_pixmap, is_temp=True)

    # ================= CAMERA LOGIC =================

    def _toggle_camera(self):
        if self._streaming:
            self._stop_camera()
        else:
            self._start_camera()
        self._update_ui_state()

    def _start_camera(self):
        """
        Starts the camera with robust handling for external cameras (like Sony A7C).
        Forces CAP_DSHOW and sets resolution to 1920x1080 to avoid connection hang.
        """
        try:
            idx = int(getattr(self, "_selected_camera_index", 0))
            print(f"[CAMERA] Starting camera worker for index: {idx}")

            if self._camera_worker is None:
                QtWidgets.QMessageBox.warning(
                    self.page, "Camera Error", "Camera worker unavailable."
                )
                return

            # Start worker which opens the device and begins emitting frames
            self._camera_worker.start_camera(idx)

            # Assume streaming once worker started; worker will emit errors if not
            self._streaming = True
            self._paused = False
            # Start inference timer (worker emits frames on its own)
            self._stream_inference_timer.start()

        except Exception as e:
            print(f"Camera Start Error: {e}")
            traceback.print_exc()

    def _stop_camera(self):
        # Stop worker and timers
        try:
            if hasattr(self, "_camera_worker") and self._camera_worker:
                try:
                    self._camera_worker.stop_camera()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self._frame_timer.stop()
        except Exception:
            pass
        try:
            self._stream_inference_timer.stop()
        except Exception:
            pass

        self._streaming = False
        self._inference_running = False

        # Release large frame buffers to free memory
        with self._frame_lock:
            self._raw_frame_np = None
            self._current_frame_np = None
        self._last_pixmap = None
        self._last_raw_result = None

        # Clear the displayed scene and any inference overlays
        self._clear_scene()

        # Clear inference table and reset stats so stopping camera removes results
        try:
            if self.ui.get("inf_table") is not None:
                self.ui["inf_table"].setRowCount(0)
        except Exception:
            pass

        try:
            self._reset_stats_labels()
        except Exception:
            pass

        # Ensure spinner/overlays hidden
        try:
            self._toggle_spinner(False)
        except Exception:
            pass

    def _on_frame_tick(self):
        """Capture frame, convert to QPixmap, display."""
        # Legacy timer-based frame capture is no longer used when CameraWorker is present.
        return

    def _toggle_capture(self):
        if not self._streaming:
            return
        self._paused = not self._paused
        self._update_ui_state()

    def _populate_source_combo(self):
        """
        Populate the source combo using QMediaDevices to get actual camera names.
        """
        combo = self.ui.get("source_combo")
        if combo is None:
            return
        combo.blockSignals(True)
        combo.clear()

        # Prefer using CameraWorker if available as it wraps QtMultimedia nicely
        devices = []
        try:
            if getattr(self, "_camera_worker", None) is not None:
                devices = self._camera_worker.get_available_cameras()
        except Exception:
            devices = []

        # Fallback to QMediaDevices
        if not devices:
            try:
                cams = QMediaDevices.videoInputs()
                for i, cam in enumerate(cams):
                    devices.append({"description": cam.description(), "index": i})
            except Exception:
                pass

        if not devices:
            combo.addItem("No cameras detected", -1)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
            return

        for d in devices:
            desc = d.get("description") or f"Camera {d.get('index')}"
            combo.addItem(desc, d.get("index"))

        combo.setCurrentIndex(0)
        self._selected_camera_index = combo.currentData() or 0
        combo.blockSignals(False)

    def _on_source_changed(self):
        combo = self.ui.get("source_combo")
        if combo is None:
            return

        # Get the index stored in the UserRole/Data
        data = combo.currentData()

        try:
            idx = int(data) if data is not None else 0
        except Exception:
            idx = 0

        print(f"[CAMERA] User selected camera index: {idx}")
        self._selected_camera_index = idx

        # If camera is currently streaming, stop and restart to switch sources
        if self._streaming:
            self._stop_camera()
            QtCore.QTimer.singleShot(200, self._start_camera)
        else:
            # Not streaming: just update the worker's selected index (no-op until start)
            pass

    # ================= IMAGE HANDLING =================

    def _upload_image(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.page, "Select Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if fname:
            self._stop_camera()
            self._update_ui_state()

            # Load raw image for color analysis
            img = cv2.imread(fname)
            if img is None:
                return

            # Reset brightness/contrast sliders to defaults for new image
            try:
                b_slider = self.ui.get("brightness_slider")
                c_slider = self.ui.get("contrast_slider")
                # Use middle of range (50) as default — keep signals blocked to avoid duplicate refresh
                if b_slider is not None:
                    b_slider.blockSignals(True)
                    try:
                        b_slider.setValue(int(self._brightness_default))
                    except Exception:
                        b_slider.setValue(50)
                    b_slider.blockSignals(False)
                if c_slider is not None:
                    c_slider.blockSignals(True)
                    try:
                        c_slider.setValue(int(self._contrast_default))
                    except Exception:
                        c_slider.setValue(50)
                    c_slider.blockSignals(False)
            except Exception:
                pass

            # Store raw and apply adjustments
            self._raw_frame_np = img.copy()
            # Apply adjustments once after resetting sliders
            try:
                self._apply_adjustments_and_refresh()
            except Exception:
                pass

            # Ensure UI buttons reflect that an image is now loaded
            self._update_ui_state()

            # Save adjusted image to a temp file and run inference on the adjusted image
            try:
                t = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                t.close()
                # _current_frame_np holds the adjusted BGR image
                if self._current_frame_np is not None:
                    cv2.imwrite(t.name, self._current_frame_np)
                    self._run_inference(t.name, is_temp=True)
                else:
                    # fallback: run inference on original file
                    self._run_inference(fname, is_temp=False)
            except Exception as e:
                print(f"Failed to run inference on uploaded image: {e}")

    def _on_worker_frame(self, frame: np.ndarray):
        """Handle frames emitted from CameraWorker."""
        try:
            if self._paused:
                return
            # Keep the raw BGR frame and apply any brightness/contrast adjustments
            with self._frame_lock:
                self._raw_frame_np = frame.copy()
            self._apply_adjustments_and_refresh()
        except Exception:
            pass

    def _on_worker_error(self, message: str):
        try:
            print(f"[CAMERA WORKER ERROR] {message}")
            QtWidgets.QMessageBox.warning(self.page, "Camera Error", str(message))
            # Ensure state consistency
            self._streaming = False
            self._inference_running = False
            try:
                self._stream_inference_timer.stop()
            except Exception:
                pass
        except Exception:
            pass

    def _display_pixmap(self, pix: QtGui.QPixmap):
        view = self.ui["cam_view"]
        if view is None:
            return

        scene = view.scene()
        if not scene:
            scene = QtWidgets.QGraphicsScene()
            # ensure scene background is black so any areas not covered by the
            # pixmap remain black (prevents white/transparent padding)
            try:
                scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
            except Exception:
                pass
            try:
                # also set the view background brush when possible
                view.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
            except Exception:
                pass
            view.setScene(scene)
        else:
            try:
                scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
            except Exception:
                pass
            try:
                view.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
            except Exception:
                pass

        # Reuse existing pixmap item if available
        pix_item = next(
            (i for i in scene.items() if isinstance(i, QtWidgets.QGraphicsPixmapItem)),
            None,
        )

        if not pix_item:
            pix_item = scene.addPixmap(pix)
        else:
            pix_item.setPixmap(pix)

        # Fit view
        try:
            view.fitInView(
                scene.itemsBoundingRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio
            )
        except Exception:
            pass

    def _clear_all(self):
        self._stop_camera()
        self._clear_scene()
        if self.ui["inf_table"] is not None:
            self.ui["inf_table"].setRowCount(0)
        self._reset_stats_labels()
        self._last_pixmap = None
        self._current_frame_np = None
        # Close large inference window if open
        try:
            if self._large_table_window is not None:
                try:
                    self._large_table_window.close()
                except Exception:
                    pass
                self._large_table_window = None
        except Exception:
            pass
        self._update_ui_state()

    def _clear_scene(self):
        if self.ui["cam_view"] is not None:
            scene = QtWidgets.QGraphicsScene()
            try:
                scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
            except Exception:
                pass
            try:
                self.ui["cam_view"].setBackgroundBrush(
                    QtGui.QBrush(QtGui.QColor(0, 0, 0))
                )
            except Exception:
                pass
            self.ui["cam_view"].setScene(scene)

    def _on_reload_clicked(self):
        """Handler for reload button: re-run inference on the currently displayed/adjusted image."""
        # Prevent concurrent inferences
        if self._inference_running:
            print("Inference already running; reload ignored.")
            return

        # Prefer the QPixmap if available
        if self._last_pixmap is not None:
            self._inference_running = True
            self._run_inference_on_pixmap(self._last_pixmap, is_temp=True)
            return

        # Otherwise, if we have a current adjusted numpy image, save and run inference
        if self._current_frame_np is not None:
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                tmp.close()
                cv2.imwrite(tmp.name, self._current_frame_np)
                self._inference_running = True
                self._run_inference(tmp.name, is_temp=True)
                return
            except Exception as e:
                print(f"Reload inference failed to write temp image: {e}")

        # Nothing to run on
        QtWidgets.QMessageBox.information(
            self.page, "No Image", "No image available to re-run inference."
        )

    def _on_view_toggled(self):
        """Toggle polygon/overlay visibility and update the view button appearance."""
        # Flip state
        self._overlays_visible = not getattr(self, "_overlays_visible", True)

        btn = self.ui.get("view_btn")
        try:
            if self._overlays_visible:
                # On state: show symbol ☉ and normal styling
                if btn is not None:
                    btn.setText("☉")
                    try:
                        btn.setProperty("designClass", "")
                        btn.style().unpolish(btn)
                        btn.style().polish(btn)
                    except Exception:
                        pass
            else:
                # Off state: show dash — and lightButton style
                if btn is not None:
                    btn.setText("—")
                    try:
                        btn.setProperty("designClass", "lightButton")
                        btn.style().unpolish(btn)
                        btn.style().polish(btn)
                    except Exception:
                        pass
        except Exception:
            pass

        # Apply visibility to existing overlays in the scene(s)
        try:
            view = self.ui.get("cam_view")
            if view is not None:
                scene = view.scene()
                if scene is not None:
                    # If a grouped inference overlay exists, toggle the group's visibility
                    grp = getattr(scene, "_inference_group", None)
                    if grp is not None:
                        try:
                            grp.setVisible(self._overlays_visible)
                            return
                        except Exception:
                            pass

                    # Fallback: toggle items tagged as inference_overlay
                    for it in scene.items():
                        try:
                            if it.data(0) == "inference_overlay":
                                it.setVisible(self._overlays_visible)
                        except Exception:
                            pass
        except Exception:
            pass

    # ================= INFERENCE LOGIC =================

    def _maybe_run_stream_inference(self):
        """Timer slot for live inference."""
        if self._inference_running or self._paused or self._last_pixmap is None:
            return
        self._inference_running = True
        self._run_inference_on_pixmap(self._last_pixmap, is_temp=True)

    def _run_inference_on_pixmap(self, pixmap: QtGui.QPixmap, is_temp: bool):
        """Helper to save pixmap to temp file and run inference."""
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.close()
            pixmap.save(tmp.name, "JPG")
            if is_temp:
                print(f"[CAMERA PAGE] running temp inference on {tmp.name}")
            self._run_inference(tmp.name, is_temp=is_temp)
        except Exception as e:
            print(f"Temp file creation failed: {e}")
            if is_temp:
                self._inference_running = False

    def _run_inference(self, path: str, is_temp: bool = False):
        """Run inference via `InferenceWorker` when available, otherwise fall back to
        the legacy threaded implementation.
        """
        # Show spinner if static image
        if not self._streaming:
            self._toggle_spinner(True)

        # Retrieve slider values
        conf_val = self.DEFAULT_CONFIDENCE
        iou_val = self.DEFAULT_IOU
        if self.ui.get("conf_slider") is not None:
            conf_val = self.ui["conf_slider"].value() / 100.0
        if self.ui.get("iou_slider") is not None:
            iou_val = self.ui["iou_slider"].value() / 100.0

        # Determine model_data (either local path or roboflow workflow id)
        model_data = self._current_local_model_path
        if not model_data:
            # extract from model_combo
            try:
                mc = self.ui.get("model_combo")
                if mc is not None:
                    idx = mc.currentIndex()
                    model_data = mc.itemData(idx)
            except Exception:
                model_data = None

        print(
            f"[INFERENCE] Running with Conf={conf_val}, IoU={iou_val}, model={model_data}"
        )

        # Mark running
        self._inference_running = True

        # Preferred path: use InferenceWorker
        if getattr(self, "_inference_worker", None) is not None:
            try:
                # Worker will emit `finished(preds, raw_result)` when done
                self._inference_worker.run_inference(
                    path, model_data, conf=conf_val, iou=iou_val, is_pixmap=False
                )
                return
            except Exception as e:
                print(f"InferenceWorker invocation failed: {e}")

        # If InferenceWorker is unavailable, surface the error clearly
        print("[INFERENCE] InferenceWorker not available — inference skipped")
        self._inference_running = False
        self._toggle_spinner(False)

    def _on_inference_worker_finished(self, preds, raw_result):
        """Handler for InferenceWorker.finished(preds, raw_result)."""
        try:
            self._inference_running = False
            self._toggle_spinner(False)

            if not preds:
                return

            # Cache raw result for slider re-filtering
            self._last_raw_result = raw_result

            # Store last preds for view details
            try:
                self._last_preds = preds or []
            except Exception:
                self._last_preds = []

            # 1. Draw overlays using raw_result when available
            try:
                if self.ui.get("cam_view") is not None and raw_result is not None:
                    scene = self.ui["cam_view"].scene()
                    if scene is not None:
                        try:
                            render_predictions_on_scene(scene, raw_result)
                        except Exception as e:
                            print(f"Overlay render failed: {e}")
            except Exception:
                pass

            # 2. Update table / stats
            try:
                self._update_table(preds)
                self._update_stats(preds)
            except Exception as e:
                print(f"Data processing failed: {e}")

        except Exception:
            pass

    def _on_inference_worker_error(self, message: str):
        try:
            print(f"[INFERENCE WORKER ERROR] {message}")
            QtWidgets.QMessageBox.warning(self.page, "Inference Error", str(message))
            self._inference_running = False
            try:
                self._toggle_spinner(False)
            except Exception:
                pass
        except Exception:
            pass

    def _refilter_from_cache(self):
        """Re-apply confidence/IoU filters on the cached raw result without re-running inference."""
        if self._last_raw_result is None:
            return

        import copy
        from mpcamera.utils.inference_utils import apply_confidence_iou_filters, parse_result_to_preds

        conf_val = self.DEFAULT_CONFIDENCE
        iou_val = self.DEFAULT_IOU
        if self.ui.get("conf_slider") is not None:
            conf_val = self.ui["conf_slider"].value() / 100.0
        if self.ui.get("iou_slider") is not None:
            iou_val = self.ui["iou_slider"].value() / 100.0

        # Work on a deep copy so we don't mutate the cached raw result
        filtered = copy.deepcopy(self._last_raw_result)
        filtered = apply_confidence_iou_filters(
            filtered, confidence_threshold=conf_val, iou_threshold=iou_val
        )
        preds = parse_result_to_preds(filtered) or []
        self._last_preds = preds
        self._update_table(preds)
        self._update_stats(preds)
        # Update overlays with filtered results
        try:
            if self.ui.get("cam_view") is not None:
                scene = self.ui["cam_view"].scene()
                if scene is not None:
                    render_predictions_on_scene(scene, filtered)
        except Exception:
            pass

    def _on_inference_finished(self, result, temp_path):
        """Handle results on Main Thread."""
        self._inference_running = False
        self._toggle_spinner(False)

        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

        if not result:
            return

        # Parse predictions and store them for use by the viewDetails button.
        try:
            preds = parse_result_to_preds(result)
            # store last preds for manual viewing
            self._last_preds = preds or []
        except Exception:
            self._last_preds = []

        # 1. Draw Overlays
        if self.ui["cam_view"] is not None:
            scene = self.ui["cam_view"].scene()
            if scene:
                try:
                    # render_predictions_on_scene expects the raw result structure
                    render_predictions_on_scene(scene, result)
                except Exception as e:
                    print(f"Overlay render failed: {e}")

        # 2. Process Data
        try:
            preds = parse_result_to_preds(result)
            self._update_table(preds)
            self._update_stats(preds)
            # do not auto-open the large window — user may open via the viewDetails button
        except Exception as e:
            print(f"Data processing failed: {e}")

    def _toggle_spinner(self, show: bool):
        view = self.ui["cam_view"]
        if view is None:
            return
        ov = ensure_overlay_for_view(view)
        if ov:
            if show:
                ov.show()
                if hasattr(ov, "_spinner"):
                    ov._spinner.start()
            else:
                if hasattr(ov, "_spinner"):
                    ov._spinner.stop()
                ov.hide()

    # ================= MEASUREMENTS & TABLE =================

    def _calculate_morphometrics(self, pred, img_w, img_h) -> Dict[str, float]:
        """Calculate physical measurements using the utility class."""
        mag = self.ui["mag_spin"].value() if self.ui["mag_spin"] is not None else 1.0

        # Delegate to the new utility class
        return ResultsManager.calculate_morphometrics(pred, img_w, img_h, mag)

    def _update_table(self, preds):
        table = self.ui["inf_table"]
        if table is None:
            return

        table.setSortingEnabled(False)
        table.setRowCount(0)

        w, h = (
            (self._last_pixmap.width(), self._last_pixmap.height())
            if self._last_pixmap
            else (0, 0)
        )

        # Ensure we have the raw image for color analysis
        current_img = self._current_frame_np

        for p in preds:
            row = table.rowCount()
            table.insertRow(row)
            stats = self._calculate_morphometrics(p, w, h)

            def set_cell(col, text, raw_data=None):
                it = QtWidgets.QTableWidgetItem(str(text))
                if raw_data is not None:
                    it.setData(QtCore.Qt.ItemDataRole.UserRole, raw_data)
                table.setItem(row, col, it)

            key = p.get("detection_id") or p.get("id") or json.dumps(p, default=str)

            set_cell(0, p.get("label", ""), key)
            set_cell(1, f"{p.get('score', 0):.2f}")

            # --- COLOR EXTRACTION ---
            color_name = ""
            if current_img is not None:
                # Get points list, handled by get_color_name
                pts = p.get("points") or extract_points_from_prediction(
                    p.get("raw") or {}
                )
                if pts:
                    try:
                        color_name = get_color_name(current_img, pts)
                    except Exception:
                        pass

            set_cell(2, color_name)

            metrics = [
                (3, "area", "μm²"),
                (4, "perimeter", "μm"),
                (5, "major", "μm"),
                (6, "minor", "μm"),
                (7, "deq", "μm"),
                (8, "skeleton", "μm"),
            ]
            for col, key_metric, unit in metrics:
                val = stats.get(key_metric)
                if val is not None:
                    set_cell(col, f"{val:.2f} {unit}", val)

    def _open_large_table_window(self, preds: List[Dict[str, Any]]):
        """Open or update a dedicated `ResultsWindow` (if available) with predictions.

        Falls back to a simple programmatic table when `ResultsWindow` is unavailable.
        """
        try:
            # Create window instance if needed
            if self._large_table_window is None or (
                ResultsWindow is not None
                and not isinstance(self._large_table_window, ResultsWindow)
            ):
                if ResultsWindow is not None:
                    win = ResultsWindow(self.main_window or self.page)
                else:
                    # Minimal fallback window
                    win = QtWidgets.QMainWindow(self.main_window or self.page)
                    win.setWindowTitle("Inference Results (Large)")
                    central = QtWidgets.QWidget()
                    win.setCentralWidget(central)
                    layout = QtWidgets.QVBoxLayout(central)
                    tbl = QtWidgets.QTableWidget()
                    headers = [
                        "Label",
                        "Score",
                        "Color",
                        "Area (μm²)",
                        "Perimeter (μm)",
                        "Major (μm)",
                        "Minor (μm)",
                        "Deq (μm)",
                        "Skeleton (μm)",
                    ]
                    tbl.setColumnCount(len(headers))
                    tbl.setHorizontalHeaderLabels(headers)
                    layout.addWidget(tbl)
                    win.table = tbl

                self._large_table_window = win
            else:
                win = self._large_table_window

            # Populate via ResultsWindow API if available
            last_pix = getattr(self, "_last_pixmap", None)
            cur_img = getattr(self, "_current_frame_np", None)

            if hasattr(win, "update_data"):
                try:
                    win.update_data(preds, last_pix, cur_img)
                except Exception as e:
                    print(f"ResultsWindow update failed: {e}")
                # Connect ResultsWindow save signal so edits from that window
                # are received back here and can be saved to Directus.
                try:
                    # Avoid multiple connections
                    if hasattr(win, "data_committed") and not getattr(
                        win, "_committed_connected", False
                    ):
                        win.data_committed.connect(self._on_results_committed)
                        win._committed_connected = True
                except Exception:
                    pass
            else:
                # Fallback table population
                tbl = getattr(win, "table", None)
                if tbl is None:
                    tbl = QtWidgets.QTableWidget()
                    win.setCentralWidget(tbl)

                tbl.setRowCount(0)
                w = last_pix.width() if last_pix else 0
                h = last_pix.height() if last_pix else 0

                for p in preds:
                    row = tbl.rowCount()
                    tbl.insertRow(row)
                    tbl.setItem(
                        row, 0, QtWidgets.QTableWidgetItem(str(p.get("label", "")))
                    )
                    score = p.get("score")
                    tbl.setItem(
                        row,
                        1,
                        QtWidgets.QTableWidgetItem(
                            f"{score:.2f}" if score is not None else ""
                        ),
                    )

                    # color
                    color_name = ""
                    if cur_img is not None:
                        try:
                            pts = p.get("points") or extract_points_from_prediction(
                                p.get("raw") or {}
                            )
                            if pts:
                                color_name = get_color_name(cur_img, pts)
                        except Exception:
                            pass
                    tbl.setItem(row, 2, QtWidgets.QTableWidgetItem(str(color_name)))

                    stats = self._calculate_morphometrics(p, w, h)
                    metrics = ["area", "perimeter", "major", "minor", "deq", "skeleton"]
                    for i, k in enumerate(metrics):
                        val = stats.get(k)
                        tbl.setItem(
                            row,
                            3 + i,
                            QtWidgets.QTableWidgetItem(
                                f"{val:.2f}" if val is not None else ""
                            ),
                        )

            try:
                win.show()
                win.raise_()
                win.activateWindow()
            except Exception:
                pass
        except Exception as e:
            print(f"Failed opening large results window: {e}")

    def _on_results_committed(self, records: List[Dict[str, Any]]):
        """Handle data emitted from the ResultsWindow Save action.

        - Update local cached preds/table so the Camera page reflects edits.
        - Build payloads expected by Directus and start the save worker.
        """
        try:
            if not records:
                return

            # Update last_preds so overlays and viewDetails reflect edits
            try:
                self._last_preds = records
            except Exception:
                pass

            # Refresh inline table and stats to reflect updated labels/verification
            try:
                self._update_table(records)
                self._update_stats(records)
            except Exception:
                pass

            # NOTE: Do NOT auto-save to Directus here. Leave uploading to the
            # camera page Save button so the user intentionally triggers uploads.
            # The camera page Save button (`_save_results`) will read from the
            # updated inline table (or `self._last_preds`) and call the upload.
            try:
                # Optionally mark that there are pending edits (UI-only)
                lbl = self.ui.get("lbl_total")
                if lbl is not None:
                    lbl.setText(str(len(records)))
            except Exception:
                pass
        except Exception as e:
            print(f"_on_results_committed error: {e}")

    def _update_stats(self, preds):
        try:
            ag = compute_aggregates(preds)
            if self.ui["lbl_total"] is not None:
                self.ui["lbl_total"].setText(str(ag.get("total", 0)))

            min_c = ag.get("min_confidence")
            max_c = ag.get("max_confidence")
            # Display confidence range only (min-max). Fallback to single value or blank.
            try:
                if self.ui["lbl_conf"] is not None:
                    if min_c is not None and max_c is not None:
                        self.ui["lbl_conf"].setText(f"{min_c:.2f}-{max_c:.2f}")
                    elif min_c is not None:
                        self.ui["lbl_conf"].setText(f"{min_c:.2f}")
                    elif max_c is not None:
                        self.ui["lbl_conf"].setText(f"{max_c:.2f}")
                    else:
                        self.ui["lbl_conf"].setText("")
            except Exception:
                pass

            cnts = ag.get("counts", {})
            mapping = {
                "lbl_frag": "fragment",
                "lbl_sheet": "sheet",
                "lbl_fiber": "fiber",
                "lbl_foam": "foam",
                "lbl_film": "film",
                "lbl_bead": "bead",
            }
            for ui_k, data_k in mapping.items():
                if self.ui[ui_k] is not None:
                    self.ui[ui_k].setText(str(cnts.get(data_k, 0)))
        except Exception:
            pass

    def _on_table_selection(self, selected, deselected):
        """Highlight overlay for selected row."""
        table = self.ui["inf_table"]
        scene = self.ui["cam_view"].scene() if self.ui["cam_view"] is not None else None
        if table is None or scene is None:
            return

        selected_keys = set()
        for idx in table.selectionModel().selectedRows():
            item = table.item(idx.row(), 0)
            if item:
                selected_keys.add(item.data(QtCore.Qt.ItemDataRole.UserRole))

        show_all = len(selected_keys) == 0
        for it in scene.items():
            if it.data(0) == "inference_overlay":
                key = it.data(1)
                it.setVisible(show_all or (key in selected_keys))

    def _reset_stats_labels(self):
        for k, v in self.ui.items():
            if k.startswith("lbl_") and v is not None:
                v.setText("")

    # ================= DATA SAVING =================

    def _save_results(self):
        if not DirectusClient:
            QtWidgets.QMessageBox.critical(
                self.page, "Error", "Directus Client unavailable."
            )
            return
        table = self.ui.get("inf_table")

        # If the inline table widget was removed (you moved it to a separate layout),
        # fall back to using the last parsed predictions stored in `self._last_preds`.
        if table is None:
            preds = getattr(self, "_last_preds", []) or []
            if not preds:
                QtWidgets.QMessageBox.information(
                    self.page, "No Data", "No measurements to save."
                )
                return

            soil_id = None
            if self.ui.get("soil_combo") is not None:
                soil_id = self.ui["soil_combo"].currentData()

            # Build payloads from preds using the same fields as the table-based flow
            payloads = []
            w = self._last_pixmap.width() if self._last_pixmap else 0
            h = self._last_pixmap.height() if self._last_pixmap else 0
            current_img = self._current_frame_np

            for p in preds:
                try:
                    stats = self._calculate_morphometrics(p, w, h)
                    # color extraction
                    color_name = ""
                    if current_img is not None:
                        try:
                            pts = p.get("points") or extract_points_from_prediction(
                                p.get("raw") or {}
                            )
                            if pts:
                                color_name = get_color_name(current_img, pts)
                        except Exception:
                            color_name = ""

                    item = {
                        "sample_source": soil_id,
                        "shape": p.get("label") or "",
                        "confidence_level": float(p.get("score") or 0),
                        "color": color_name,
                        "area_um2": stats.get("area"),
                        "perimeter_um": stats.get("perimeter"),
                        "major_axis_um": stats.get("major"),
                        "minor_axis_um": stats.get("minor"),
                        "equivalent_circular_diameter_um": stats.get("deq"),
                        "skeleton_length_um": stats.get("skeleton"),
                    }
                    # Include geometry so the save worker can crop per-particle
                    if p.get("points"):
                        item["points"] = p.get("points")
                    if p.get("bbox"):
                        item["bbox"] = p.get("bbox")

                    payloads.append({k: v for k, v in item.items() if v is not None})
                except Exception:
                    continue

            if not payloads:
                QtWidgets.QMessageBox.information(
                    self.page, "No Data", "No measurements to save."
                )
                return

            self._start_save_worker(payloads)
            return

        # Otherwise use the table widget as before
        rows = [idx.row() for idx in table.selectionModel().selectedRows()]
        if not rows:
            rows = range(table.rowCount())

        if not rows:
            QtWidgets.QMessageBox.information(
                self.page, "No Data", "No measurements to save."
            )
            return

        soil_id = None
        if self.ui.get("soil_combo") is not None:
            soil_id = self.ui["soil_combo"].currentData()

        payloads = []

        for r in rows:

            def get_val(c):
                it = table.item(r, c)
                return it.data(QtCore.Qt.ItemDataRole.UserRole) if it else None

            item = {
                "sample_source": soil_id,
                "shape": table.item(r, 0).text(),
                "confidence_level": float(table.item(r, 1).text() or 0),
                "color": table.item(r, 2).text(),
                "area_um2": get_val(3),
                "perimeter_um": get_val(4),
                "major_axis_um": get_val(5),
                "minor_axis_um": get_val(6),
                "equivalent_circular_diameter_um": get_val(7),
                "skeleton_length_um": get_val(8),
            }
            # Try to augment with geometry from the matching prediction in `_last_preds`.
            try:
                key = table.item(r, 0).data(QtCore.Qt.ItemDataRole.UserRole)
                if key and getattr(self, "_last_preds", None):
                    match = None
                    for pp in getattr(self, "_last_preds", []):
                        k = (
                            pp.get("detection_id")
                            or pp.get("id")
                            or json.dumps(pp, default=str)
                        )
                        if str(k) == str(key):
                            match = pp
                            break
                    if match:
                        if match.get("points"):
                            item["points"] = match.get("points")
                        if match.get("bbox"):
                            item["bbox"] = match.get("bbox")
            except Exception:
                pass

            payloads.append({k: v for k, v in item.items() if v is not None})

        self._start_save_worker(payloads)

    def _start_save_worker(self, payloads):
        """Spawns worker to upload image and records."""

        # Prepare cropped images for each payload (if geometry available).
        # For each payload we may add an internal `_image_path` key pointing to a
        # temporary file containing the cropped image. If no per-payload crop is
        # possible, fall back to saving the full image as before and pass it as
        # `img_path` for a single upload used by all records.
        img_path = None
        try:
            per_payload_images = False
            if self._last_pixmap:
                for p in payloads:
                    pts = p.get("points") or []
                    bbox = p.get("bbox") or []
                    if not pts and not bbox:
                        continue

                    try:
                        # Compute crop coordinates (match ResultsWindow logic)
                        if pts:
                            xs = [int(x) for x, _ in pts]
                            ys = [int(y) for _, y in pts]
                            x0, y0 = int(min(xs)), int(min(ys))
                            x1, y1 = int(max(xs)), int(max(ys))
                        else:
                            x0, y0, w, h = [int(v) for v in bbox]
                            x1, y1 = x0 + w, y0 + h

                        pad = 30
                        x0 = max(0, x0 - pad)
                        y0 = max(0, y0 - pad)
                        x1 = min(self._last_pixmap.width(), x1 + pad)
                        y1 = min(self._last_pixmap.height(), y1 + pad)

                        rect = QtCore.QRect(x0, y0, x1 - x0, y1 - y0)
                        cropped = self._last_pixmap.copy(rect)

                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                        tmp.close()
                        # Save as PNG to avoid compression artifacts
                        cropped.save(tmp.name, "PNG")
                        p["_image_path"] = tmp.name
                        per_payload_images = True
                    except Exception:
                        # skip crop failures for this payload
                        continue

            if not per_payload_images and self._last_pixmap:
                try:
                    t = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    t.close()
                    self._last_pixmap.save(t.name, "JPG")
                    img_path = t.name
                except Exception as e:
                    print(f"Error saving temp image: {e}")
        except Exception:
            # Best-effort: continue without images if anything goes wrong
            img_path = None

        def worker():
            count = 0
            try:
                # Initialize client inside the thread
                client = DirectusClient()

                # Delegate heavy lifting to the new utility class
                count = ResultsManager.process_upload(client, payloads, img_path)

            except Exception as e:
                print(f"Save Worker Error: {e}")
                traceback.print_exc()

            self.data_saved_signal.emit(count)

        Thread(target=worker, daemon=True).start()

    def _on_save_finished(self, count):
        if count > 0:
            QtWidgets.QMessageBox.information(
                self.page, "Saved", f"Successfully saved {count} records."
            )
        else:
            QtWidgets.QMessageBox.warning(
                self.page, "Error", "Failed to save records. Check console."
            )

    def _update_ui_state(self):
        ui = self.ui
        streaming = self._streaming
        has_img = self._last_pixmap is not None

        if ui["cam_btn"] is not None:
            ui["cam_btn"].setText("Stop Camera" if streaming else "Start Camera")
        if ui["cap_btn"] is not None:
            ui["cap_btn"].setEnabled(streaming)
            ui["cap_btn"].setText("Resume" if self._paused else "Capture")
        if ui["img_btn"] is not None:
            ui["img_btn"].setEnabled(not streaming)
        if ui["clear_btn"] is not None:
            ui["clear_btn"].setEnabled(not streaming and has_img)


# ================= ENTRY POINT =================


def setup(camera_page: QtWidgets.QWidget, main_window: QtWidgets.QMainWindow):
    """Called by main application to initialize the Camera Page."""
    try:
        camera_page._controller = CameraPageController(camera_page, main_window)
        print("CameraPageController initialized.")
    except Exception as e:
        print(f"camera_page.setup failed: {e}")
        traceback.print_exc()
