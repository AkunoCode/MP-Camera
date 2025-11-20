import cv2
import json
import os
import tempfile
import traceback
import threading
import numpy as np
from threading import Thread
from typing import Optional, List, Dict, Any

from PyQt6 import QtWidgets, QtCore, QtGui

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
from mpcamera.utils.camera_utils import extract_directus_items, get_site_id_from_sample
from mpcamera.utils.prediction_utils import extract_points_from_prediction
from mpcamera.ui.overlays import ensure_overlay_for_view, render_predictions_on_scene
from mpcamera.utils.inference_utils import parse_result_to_preds, compute_aggregates
from mpcamera.utils.um_per_pixel import calculate_micrometers_per_pixel
from mpcamera.utils.morphometrics import (
    calculate_area_um2,
    calculate_perimeter_um,
    calculate_major_axis_um,
    calculate_minor_axis_um,
    calculate_equivalent_circular_diameter,
    calculate_skeleton_length_um,
)


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
    DEFAULT_MODEL = ("YOLOv11", "detect-count-and-visualize-2")
    ALT_MODEL = ("RF-DETR-SEG", "detect-count-and-visualize")

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
        self._cached_soils: List[Dict] = []

        # --- Timers ---
        self._frame_timer = QtCore.QTimer()
        self._frame_timer.setInterval(self.FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_frame_tick)

        self._stream_inference_timer = QtCore.QTimer()
        self._stream_inference_timer.setInterval(self.INFERENCE_INTERVAL_MS)
        self._stream_inference_timer.timeout.connect(self._maybe_run_stream_inference)

        # --- Init Sequence ---
        self.ui = self._find_ui_elements()
        self._replace_graphics_view()
        self._init_ui_defaults()
        self._setup_connections()

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

        # Buttons
        if ui["cam_btn"] is not None:
            ui["cam_btn"].clicked.connect(self._toggle_camera)
        if ui["cap_btn"] is not None:
            ui["cap_btn"].clicked.connect(self._toggle_capture)
        if ui["clear_btn"] is not None:
            ui["clear_btn"].clicked.connect(self._clear_all)
        if ui["img_btn"] is not None:
            ui["img_btn"].clicked.connect(self._upload_image)
        if ui["save_btn"] is not None:
            ui["save_btn"].clicked.connect(self._save_results)

        # Worker signals
        self.inference_finished_signal.connect(self._on_inference_finished)
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
                (QtWidgets.QPushButton, QtWidgets.QComboBox, QtWidgets.QTableWidget),
            ):
                widget.setCursor(hand_cursor)

        # Init Model Combo
        combo = self.ui["model_combo"]
        if combo is not None:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(*self.DEFAULT_MODEL)
            combo.addItem(*self.ALT_MODEL)

            # Sync with current Roboflow default if available
            if RoboflowClient:
                try:
                    current_wf = RoboflowClient.get_default().workflow
                    idx = combo.findData(current_wf)
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                except Exception:
                    combo.setCurrentIndex(0)
            combo.blockSignals(False)

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

        except ImportError:
            print("ZoomableGraphicsView not found, using default.")
        except Exception as e:
            print(f"View replacement failed: {e}")

    # ================= DATA LOADING (Restored Robust Logic) =================

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
            if sites:
                print(f"[CAMERA PAGE] sites sample={sites[:3]}")

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

        print(
            f"[CAMERA PAGE] update_farm_combo: combo_present={combo is not None} items_before={combo.count() if combo is not None else 'N/A'}"
        )

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
                print(
                    f"[CAMERA PAGE] added farm item idx={idx} id={item.get('id')} name={name}"
                )
            except Exception as e:
                print(f"[CAMERA PAGE] failed to add farm item idx={idx} error={e}")

        combo.setCurrentIndex(-1)
        combo.blockSignals(False)

        print(f"[CAMERA PAGE] farm_combo items_after={combo.count()}")

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
                    print(f"[CAMERA PAGE] added soil item id={sid} site={s_site}")
                except Exception as e:
                    print(f"[CAMERA PAGE] failed to add soil item error={e}")

        combo.blockSignals(False)
        print(f"[CAMERA PAGE] soil_combo items_after={count} (Filter: {site_id})")

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

    def _on_model_changed(self):
        """Update global Roboflow config and re-run inference if image loaded."""
        if self.ui["model_combo"] is None:
            return

        idx = self.ui["model_combo"].currentIndex()
        wf = self.ui["model_combo"].itemData(idx)

        if RoboflowClient and wf:
            try:
                RoboflowClient.get_default().workflow = wf
                print(f"Roboflow workflow set to {wf}")
            except Exception:
                pass

        # Re-run inference if static image exists
        if self._last_pixmap is not None:
            print(f"[CAMERA PAGErunning inference due to model change")
            self._run_inference_on_pixmap(self._last_pixmap, is_temp=True)

    # ================= CAMERA LOGIC =================

    def _toggle_camera(self):
        if self._streaming:
            self._stop_camera()
        else:
            self._start_camera()
        self._update_ui_state()

    def _start_camera(self):
        try:
            # Prefer DSHOW on Windows
            self._vc = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self._vc.isOpened():
                self._vc = cv2.VideoCapture(0)

            if self._vc.isOpened():
                self._streaming = True
                self._paused = False
                self._frame_timer.start()
                self._stream_inference_timer.start()
            else:
                print("Failed to open camera.")
                self._vc = None
        except Exception as e:
            print(f"Camera Start Error: {e}")

    def _stop_camera(self):
        self._frame_timer.stop()
        self._stream_inference_timer.stop()
        if self._vc:
            self._vc.release()
        self._vc = None
        self._streaming = False
        self._inference_running = False
        self._clear_scene()

    def _on_frame_tick(self):
        """Capture frame, convert to QPixmap, display."""
        if not self._vc or self._paused:
            return

        ret, frame = self._vc.read()
        if ret:
            try:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                qimg = QtGui.QImage(
                    frame_rgb.data, w, h, ch * w, QtGui.QImage.Format.Format_RGB888
                )
                # Copy to avoid memory issues
                self._last_pixmap = QtGui.QPixmap.fromImage(qimg.copy())
                self._display_pixmap(self._last_pixmap)
            except Exception:
                pass

    def _toggle_capture(self):
        if not self._streaming:
            return
        self._paused = not self._paused
        self._update_ui_state()

    # ================= IMAGE HANDLING =================

    def _upload_image(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.page, "Select Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if fname:
            self._stop_camera()
            self._update_ui_state()

            pix = QtGui.QPixmap(fname)
            if not pix.isNull():
                self._last_pixmap = pix
                self._display_pixmap(pix)
                self._run_inference(fname, is_temp=False)

    def _display_pixmap(self, pix: QtGui.QPixmap):
        view = self.ui["cam_view"]
        if view is None:
            return

        scene = view.scene()
        if not scene:
            scene = QtWidgets.QGraphicsScene()
            view.setScene(scene)

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
        self._update_ui_state()

    def _clear_scene(self):
        if self.ui["cam_view"] is not None:
            self.ui["cam_view"].setScene(QtWidgets.QGraphicsScene())

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
        """Spawns background thread for Roboflow."""
        # Show spinner if static image
        if not self._streaming:
            self._toggle_spinner(True)

        def worker():
            result = None
            try:
                if RoboflowClient:
                    client = RoboflowClient.get_default()
                    result = client.run_workflow(path)
            except Exception as e:
                print(f"Inference Error: {e}")
            finally:
                self.inference_finished_signal.emit(result, path if is_temp else "")

        Thread(target=worker, daemon=True).start()

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

        # 1. Draw Overlays
        if self.ui["cam_view"] is not None:
            scene = self.ui["cam_view"].scene()
            if scene:
                try:
                    render_predictions_on_scene(scene, result)
                except Exception as e:
                    print(f"Overlay render failed: {e}")

        # 2. Process Data
        try:
            preds = parse_result_to_preds(result)
            self._update_table(preds)
            self._update_stats(preds)
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
        """Calculate physical measurements."""
        mag = self.ui["mag_spin"].value() if self.ui["mag_spin"] is not None else 1.0
        um_per_px = None

        if img_w and img_h:
            try:
                res = calculate_micrometers_per_pixel(mag, img_w, img_h)
                um_per_px = float(res.get("average_multiplier_um", 0))
            except Exception:
                pass

        stats = {
            k: None for k in ["area", "perimeter", "major", "minor", "deq", "skeleton"]
        }
        stats["um_per_px"] = um_per_px

        pts = (
            pred.get("points")
            or extract_points_from_prediction(pred.get("raw") or {})
            or []
        )

        if len(pts) < 3 or not um_per_px:
            return stats

        try:
            arr = np.array(pts, dtype=float)

            # Geometry calcs (Simplified logic)
            x, y = arr[:, 0], arr[:, 1]
            area_px = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

            diffs = np.diff(arr, axis=0, append=arr[:1])
            perim_px = float(np.sum(np.hypot(diffs[:, 0], diffs[:, 1])))

            # PCA
            pts_c = arr - arr.mean(axis=0)
            evals, evecs = np.linalg.eigh(np.cov(pts_c.T))
            order = np.argsort(evals)[::-1]
            evecs = evecs[:, order]

            proj1 = pts_c.dot(evecs[:, 0])
            proj2 = pts_c.dot(evecs[:, 1])
            major_px = float(proj1.max() - proj1.min())
            minor_px = float(proj2.max() - proj2.min())

            # Conversions
            stats["area"] = calculate_area_um2(area_px, um_per_px)
            stats["perimeter"] = calculate_perimeter_um(perim_px, um_per_px)
            stats["major"] = calculate_major_axis_um(major_px, um_per_px)
            stats["minor"] = calculate_minor_axis_um(minor_px, um_per_px)
            stats["deq"] = calculate_equivalent_circular_diameter(
                stats["area"] or 0, um_per_px
            )
            stats["skeleton"] = calculate_skeleton_length_um(major_px, um_per_px)
        except Exception:
            pass

        return stats

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
            set_cell(2, "")

            metrics = [
                (3, "area", "μm²"),
                (4, "perimeter", "μm"),
                (5, "major", "μm"),
                (6, "minor", "μm"),
                (7, "deq", "μm"),
                (8, "skeleton", "μm"),
            ]
            for col, key, unit in metrics:
                val = stats.get(key)
                if val is not None:
                    set_cell(col, f"{val:.2f} {unit}", val)

    def _update_stats(self, preds):
        try:
            ag = compute_aggregates(preds)
            if self.ui["lbl_total"] is not None:
                self.ui["lbl_total"].setText(str(ag.get("total", 0)))

            ave = ag.get("ave_confidence", 0)
            if self.ui["lbl_conf"] is not None:
                self.ui["lbl_conf"].setText(f"{ave:.2f}")

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

        table = self.ui["inf_table"]
        if table is None:
            return

        rows = [idx.row() for idx in table.selectionModel().selectedRows()]
        if not rows:
            rows = range(table.rowCount())

        if not rows:
            QtWidgets.QMessageBox.information(
                self.page, "No Data", "No measurements to save."
            )
            return

        soil_id = None
        if self.ui["soil_combo"] is not None:
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
                "area_um2": get_val(3),
                "perimeter_um": get_val(4),
                "major_axis_um": get_val(5),
                "minor_axis_um": get_val(6),
                "equivalent_circular_diameter_um": get_val(7),
                "skeleton_length_um": get_val(8),
            }
            payloads.append({k: v for k, v in item.items() if v is not None})

        self._start_save_worker(payloads)

    def _start_save_worker(self, payloads):
        """Spawns worker to upload image and records."""
        img_path = None
        if self._last_pixmap:
            t = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            t.close()
            self._last_pixmap.save(t.name, "JPG")
            img_path = t.name

        def worker():
            count = 0
            try:
                client = DirectusClient()
                img_id = None

                if img_path:
                    try:
                        resp = client.upload_file(img_path)
                        if isinstance(resp, dict) and "data" in resp:
                            img_id = resp["data"].get("id")
                    finally:
                        os.remove(img_path)

                for p in payloads:
                    if img_id:
                        p["image"] = img_id
                    client.create_microplastic(p)
                    count += 1
            except Exception as e:
                print(f"Save Worker Error: {e}")

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
