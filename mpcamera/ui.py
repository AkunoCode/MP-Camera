from PyQt5 import uic
from PyQt5.QtCore import (
    QUrl,
    QEvent,
    QObject,
    QTimer,
    Qt,
    QThread,
    pyqtSignal,
    pyqtSlot,
    QMetaObject,
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QSizePolicy, QMainWindow, QFileDialog
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
import cv2
import os
import logging

from mpcamera.directus.directus import DirectusClient

# Note: do NOT import `inference` at module import time — it can run
# initialization code that affects global state (and can interfere with
# PyQt's XML parsing). The worker performs a lazy import when started.

# Optional: enable remote debugging for Chromium (useful for devtools)
# Port can be opened in a browser: http://localhost:9222
os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9222")

# Load the UI type so the MainWindow class inherits the exact base class
# (e.g. QMainWindow) defined in the .ui file. This avoids nesting a
# QMainWindow inside another window.
ui_path = os.path.join(os.path.dirname(__file__), "SoilSight.ui")
# Use runtime loading to avoid loadUiType parsing issues on some systems
BaseClass = QMainWindow


class MainWindow(BaseClass):
    """Main window that directly uses the QMainWindow from the .ui file.

    This class loads the .ui at runtime with `uic.loadUi` and replaces the
    `webEnginePlaceholder` widget with an actual `QWebEngineView` instance.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # load UI at runtime to avoid loadUiType parsing issues
        try:
            uic.loadUi(ui_path, self)
        except Exception:
            # If loadUi fails, show error so it's debuggable instead of
            # silently continuing with an uninitialized UI.
            import traceback

            print("uic.loadUi failed:")
            traceback.print_exc()
            # Fall back to any earlier behavior if loadUi fails
            try:
                if hasattr(self, "setupUi"):
                    self.setupUi(self)
            except Exception:
                pass
        # Enforce the exact window size from the .ui: 1174x766
        try:
            self.setFixedSize(1174, 766)
        except Exception:
            # fall back to resize if fixed size not available
            self.resize(1174, 766)

        # Ensure the camera view label keeps the intended size (658x432)
        try:
            # Use _find_widget to support suffixes like `_3`/`_4` in the .ui
            cam_label = (
                self._find_widget("cameraView")
                if hasattr(self, "_find_widget")
                else getattr(self, "cameraView", None)
            )
            if cam_label is not None:
                try:
                    cam_label.setFixedSize(658, 432)
                    cam_label.setMinimumSize(658, 432)
                    cam_label.setMaximumSize(658, 432)
                    cam_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                    cam_label.setContentsMargins(0, 0, 0, 0)
                    cam_label.setAlignment(Qt.AlignCenter)
                    cam_label.setScaledContents(False)
                    cam_label.updateGeometry()
                except Exception:
                    cam_label.resize(658, 432)
        except Exception:
            pass

        # Embed QWebEngineView where the placeholder widget is defined in the .ui
        try:
            # Small custom page to capture JS console messages for debugging
            class LoggingWebPage(QWebEnginePage):
                def javaScriptConsoleMessage(
                    self, level, message, lineNumber, sourceID
                ):
                    try:
                        print(
                            f"JS console (level={level}) {sourceID}:{lineNumber} -> {message}"
                        )
                    except Exception:
                        print("JS console:", message)

            placeholder = getattr(self, "webEnginePlaceholder_7", None)
            if placeholder is not None:
                container = placeholder.parent() or self
                placeholder.deleteLater()
            else:
                container = getattr(
                    self, "chart_page", getattr(self, "centralwidget", self)
                )

            # create the view and use the logging page
            self.webEngineView = QWebEngineView(container)
            self.webEngineView.setObjectName("webEngineView")
            self.webEngineView.setPage(LoggingWebPage(self.webEngineView))

            # Place the view inside the container's layout if present, otherwise
            # size it to the container and install a resize filter so it follows size.
            try:
                layout = container.layout()
                if layout is not None:
                    layout.addWidget(self.webEngineView)
                else:
                    # no layout: parent the view and match geometry
                    self.webEngineView.setParent(container)
                    try:
                        self.webEngineView.setGeometry(container.rect())
                    except Exception:
                        pass

                # simple load-finished handler to fall back if navigation fails
                def _on_load_finished(ok: bool):
                    if not ok:
                        print("WebEngineView failed to load; loading example.com")
                        try:
                            self.webEngineView.setUrl(QUrl("https://example.com"))
                        except Exception:
                            pass

                # safe target URL (can be changed to a local asset if available)
                target_url = QUrl("https://example.com")

                try:
                    self.webEngineView.loadFinished.connect(_on_load_finished)
                    self.webEngineView.urlChanged.connect(
                        lambda u: print(f"WebView: urlChanged {u.toString()}")
                    )
                except Exception as e:
                    print("Failed to connect load signals:", e)

            except Exception as e:
                print("Failed to place webEngineView in container:", e)

            # finally set the URL to begin loading
            try:
                self.webEngineView.setUrl(target_url)
            except Exception:
                pass
            # --- Navigation: connect sidebar buttons to stackedWidget pages ---
            # Map known button objectNames to the page widget names defined in the .ui
            nav_map = {
                # designer-generated names found in SoilSight.ui
                "pushButton_4": "farm_page_7",
                "pushButton_5": "sample_page",
                "pushButton_3": "camera_page_7",
                "pushButton_2": "chart_page",
                # semantic names the project may use
                "farmNavButton": "farm_page_7",
                "sampleNavButton": "sample_page",
                "cameraNavButton": "camera_page_7",
                "chartNavButton": "chart_page",
                "homeNavButton": "home_page",
            }

            def _connect_nav_button(btn_obj, page_widget):
                try:
                    btn_obj.clicked.connect(
                        lambda _checked=False, p=page_widget: self.stackedWidget.setCurrentWidget(
                            p
                        )
                    )
                except Exception:
                    # ignore if button has no clicked signal
                    pass

            for btn_name, page_name in nav_map.items():
                btn = getattr(self, btn_name, None)
                page = getattr(self, page_name, None)
                if btn is not None and page is not None:
                    _connect_nav_button(btn, page)
            # --- Camera streaming support ---
            # cameraView should be a QLabel on the `camera_page` that will
            # receive frames from OpenCV. We'll auto-start the camera when the
            # camera page becomes the current stacked widget page and stop it
            # when leaving.
            self._camera_cap = None
            self._camera_timer = QTimer(self)
            self._camera_timer.setInterval(30)  # ~33 FPS
            self._camera_timer.timeout.connect(self._read_camera_frame)

            def _on_stacked_changed(index):
                try:
                    current = self.stackedWidget.currentWidget()
                    # Handle possible suffixes like camera_page_7 by checking objectName
                    if current is not None:
                        name = getattr(current, "objectName", lambda: "")()
                        if name.startswith("camera_page") or name == "camera_page":
                            # start camera if not running
                            if self._camera_cap is None:
                                self.start_camera(0)
                            return
                    # otherwise stop camera
                    self.stop_camera()
                except Exception:
                    pass

            try:
                self.stackedWidget.currentChanged.connect(_on_stacked_changed)
            except Exception:
                # If stackedWidget isn't present for some reason, don't crash
                pass
        except Exception as e:
            # Keep UI functional even if WebEngine isn't available; print error.
            print("Failed to create QWebEngineView:", e)

        # After the UI is created and event loop starts, populate the farms
        # combo box from Directus. Use a short singleShot to avoid running
        # a network request before the window is shown.
        try:
            QTimer.singleShot(200, self._load_sites_from_directus)
        except Exception:
            pass

        # Connect farm selection change to update the sample list
        try:
            combo = getattr(self, "farmComboBox", None)
            if combo is not None:
                combo.currentIndexChanged.connect(self._on_farm_changed)
        except Exception:
            pass

        # Populate model choices and wire model change handling
        try:
            try:
                self._populate_model_combo()
            except Exception:
                pass
            mcb = self._find_widget("modelComboBox")
            if mcb is not None:
                mcb.currentIndexChanged.connect(self._on_model_changed)
        except Exception:
            pass

        # Live inference controls
        try:
            # wire video tab live inference button (try multiple naming patterns)
            lb = getattr(self, "liveInferenceButton_2", None) or getattr(
                self, "liveInferenceButton", None
            )
            if lb is not None:
                lb.clicked.connect(self._toggle_live_inference)
        except Exception:
            pass

        # Upload image button -> select image (image inference tab)
        try:
            up_btn = (
                getattr(self, "uploadImgButton_2", None)
                or getattr(self, "uploadImgButton", None)
                or getattr(self, "uploadImageButton_2", None)
                or getattr(self, "uploadImageButton", None)
            )
            if up_btn is not None:
                up_btn.clicked.connect(self._on_upload_image_clicked)
        except Exception:
            pass

        # Run image inference button (image tab) - support renamed `imageInferenceButton`
        try:
            run_btn = (
                getattr(self, "imageInferenceButton_2", None)
                or getattr(self, "imageInferenceButton", None)
                or getattr(self, "runImgInferenceButton_2", None)
                or getattr(self, "runImgInferenceButton", None)
            )
            if run_btn is not None:
                run_btn.clicked.connect(self._run_image_inference_clicked)
        except Exception:
            pass

        # Ensure Run button is enabled only when a model is selected and an image uploaded
        try:
            # connect model changes to update run button state
            mcb = self._find_widget("modelComboBox")
            if mcb is not None:
                try:
                    mcb.currentIndexChanged.connect(self._update_run_button_state)
                except Exception:
                    pass
            # update initial state
            try:
                self._update_run_button_state()
            except Exception:
                pass
        except Exception:
            pass

        # Capture (freeze) button in video tab
        try:
            cap_btn = getattr(self, "captureButton_2", None) or getattr(
                self, "captureButton", None
            )
            if cap_btn is not None:
                cap_btn.clicked.connect(self._freeze_video_inference)
        except Exception:
            pass

        # Tab widget change handling (auto-start/stop camera)
        try:
            if getattr(self, "tabWidget", None) is not None:
                self.tabWidget.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

        # Enable sorting on the inference table if present
        try:
            tbl = self._find_widget("inferenceTable") or getattr(
                self, "inferenceTable", None
            )
            if tbl is not None:
                try:
                    tbl.setSortingEnabled(True)
                except Exception:
                    pass
        except Exception:
            pass

        # placeholders for inference thread/worker
        self._inference_thread = None
        self._inference_worker = None
        # Separate tracking for single-image inference (reuses same worker class)
        self._image_inference_thread = None
        self._image_inference_worker = None

    # Camera control methods
    def start_camera(self, index=0):
        """Start capturing from camera index and display in `cameraView` label."""
        try:
            if self._camera_cap is not None:
                return
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                # Try without CAP_DSHOW on some systems
                cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                print(f"Unable to open camera index {index}")
                return
            self._camera_cap = cap
            self._camera_timer.start()
            print(f"Camera started (index={index})")
        except Exception as e:
            print("start_camera failed:", e)

    def _find_widget(self, base_name: str):
        """Find a widget with common suffixes used in the UI revisions.

        Tries suffixes `_2`, `_3`, `_4`, then no suffix. Returns the first
        attribute found or None.
        """
        for suf in ("_2", "_3", "_4", ""):
            obj = getattr(self, f"{base_name}{suf}", None)
            if obj is not None:
                return obj
        return None

    def stop_camera(self):
        """Stop camera capture and release resources."""
        try:
            if self._camera_timer.isActive():
                self._camera_timer.stop()
            if self._camera_cap is not None:
                try:
                    self._camera_cap.release()
                except Exception:
                    pass
                self._camera_cap = None
                print("Camera stopped")
        except Exception as e:
            print("stop_camera failed:", e)

    def _read_camera_frame(self):
        """Read a frame from the camera and display it in `cameraView`."""
        try:
            cap = self._camera_cap
            if cap is None:
                return
            ret, frame = cap.read()
            if not ret or frame is None:
                return
            # Convert BGR -> RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            # Try to find the camera view label using the helper that handles
            # different suffix variants (e.g. cameraView_3, cameraView_4).
            label = self._find_widget("cameraView") or getattr(self, "cameraView", None)
            if label is None:
                # No label to show frames into; stop camera to avoid busy loop
                self.stop_camera()
                return
            pix = QPixmap.fromImage(qimg)
            # Prefer the label's actual size; fall back to the desired fixed size
            try:
                target_w = label.width() or 658
                target_h = label.height() or 432
            except Exception:
                target_w, target_h = 658, 432

            scaled = pix.scaled(
                target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            label.setPixmap(scaled)
            label.repaint()
        except Exception as e:
            print("_read_camera_frame error:", e)

    def _load_sites_from_directus(self):
        """Fetch sites from Directus and populate `farmComboBox`.

        The combo box item text will be the site/farm name and the
        userData will be the Directus record id.
        """
        logger = logging.getLogger(__name__)
        combo = getattr(self, "farmComboBox", None)
        if combo is None:
            logger.debug("No farmComboBox found in UI; skipping Directus load")
            return

        try:
            client = DirectusClient()
        except Exception as e:
            logger.debug("DirectusClient init failed: %s", e)
            return

        try:
            # Request only the id and farm/site name fields to reduce payload
            params = {"fields": "id,farm_name,site_name", "limit": -1}
            resp = client.get_sites(params=params)
            # Directus typically returns {"data": [...]}
            if isinstance(resp, dict) and "data" in resp:
                sites = resp.get("data", [])
            elif isinstance(resp, list):
                sites = resp
            else:
                sites = []
        except Exception as e:
            logger.debug("Failed to fetch sites from Directus: %s", e)
            sites = []

        try:
            combo.clear()
            combo.addItem("Select a farm", None)
            for s in sites:
                # support multiple possible name fields for resilience
                name = s.get("farm_name") or s.get("site_name") or s.get("name")
                if not name:
                    name = str(s.get("id", ""))
                combo.addItem(name, s.get("id"))
        except Exception as e:
            logger.debug("Failed to populate farmComboBox: %s", e)

    def _on_farm_changed(self, index: int):
        """Handle farm selection changes and load soilsamples for the chosen site."""
        try:
            combo = getattr(self, "farmComboBox", None)
            sample_combo = getattr(self, "sampleComboBox", None)
            if combo is None or sample_combo is None:
                return
            # Use currentData() which returns the userData set when adding items
            site_id = combo.itemData(index)
            # If index corresponds to the placeholder (None), clear samples
            if site_id in (None, "", 0):
                sample_combo.clear()
                sample_combo.addItem("Select a sample", None)
                return
            # Load samples for this site id
            self._load_samples_for_site(site_id)
        except Exception as e:
            logging.getLogger(__name__).debug("_on_farm_changed error: %s", e)

    def _load_samples_for_site(self, site_id):
        """Fetch soilsamples from Directus filtered by `site` and populate `sampleComboBox`.

        Uses Directus filter parameter `filter[site][_eq]=<id>` to request only
        samples that belong to the chosen site.
        """
        logger = logging.getLogger(__name__)
        combo = getattr(self, "sampleComboBox", None)
        if combo is None:
            logger.debug("No sampleComboBox found; skipping sample load")
            return

        try:
            client = DirectusClient()
        except Exception as e:
            logger.debug("DirectusClient init failed for samples: %s", e)
            return

        try:
            # Request id and date_collected so we can build the display string
            params = {
                "filter[site][_eq]": site_id,
                "fields": "id,date_collected",
                "limit": -1,
            }
            resp = client.get_soilsamples(params=params)
            if isinstance(resp, dict) and "data" in resp:
                samples = resp.get("data", [])
            elif isinstance(resp, list):
                samples = resp
            else:
                samples = []
        except Exception as e:
            logger.debug("Failed to fetch soilsamples from Directus: %s", e)
            samples = []

        try:
            combo.clear()
            combo.addItem("Select a sample", None)
            for s in samples:
                sid = s.get("id")
                raw_date = s.get("date_collected")
                # Normalize ISO date (YYYY-MM-DD) to DD-MM-YYYY for display
                display_date = ""
                try:
                    if raw_date:
                        # accept full ISO or date-only strings
                        iso = str(raw_date).strip()
                        date_part = iso.split("T")[0]
                        y, m, d = date_part.split("-")
                        display_date = f"{d}-{m}-{y}"
                except Exception:
                    display_date = str(raw_date)

                text = f"Soil Sample {sid}"
                if display_date:
                    text = f"{text} - {display_date}"

                combo.addItem(text, sid)
        except Exception as e:
            logger.debug("Failed to populate sampleComboBox: %s", e)

    # --- Model selection and persistence ----------------------------------
    def _populate_model_combo(self):
        """Populate the modelComboBox with available models.

        The mapping here is kept simple; keys are display names and values
        are the Roboflow workflow ids that will be written to
        `ROBOFLOW_WORKFLOW` when selected.
        """
        try:
            mapping = {
                "RF-DETR-SEG": "detect-count-and-visualize",
                "YOLOv11": "detect-count-and-visualize-2",
            }
            combo = self._find_widget("modelComboBox")
            if combo is None:
                return
            combo.clear()
            for name, wf in mapping.items():
                combo.addItem(name, wf)

            # Try to set the current index from environment if present
            cur = os.environ.get("ROBOFLOW_WORKFLOW")
            if cur:
                for i in range(combo.count()):
                    try:
                        if combo.itemData(i) == cur:
                            combo.setCurrentIndex(i)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    def _on_model_changed(self, index: int):
        """Handle model selection change by updating env and persisting .env."""
        try:
            sender = self.sender() if hasattr(self, "sender") else None
            combo = sender or self._find_widget("modelComboBox")
            if combo is None:
                return
            wf = combo.itemData(index)
            if not wf:
                return
            # Update runtime env
            os.environ["ROBOFLOW_WORKFLOW"] = str(wf)
            # Persist to project .env
            try:
                self._persist_env_var("ROBOFLOW_WORKFLOW", str(wf))
            except Exception:
                pass
            # Update run button state when model changes
            try:
                self._update_run_button_state()
            except Exception:
                pass
        except Exception:
            pass

    def _persist_env_var(self, key: str, value: str):
        """Persist a single KEY=VALUE into the repository `.env` file.

        If the key exists it will be replaced; otherwise appended. This is a
        best-effort helper and will not modify other environment files.
        """
        try:
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            env_path = os.path.join(root, ".env")
            # If .env doesn't exist, create it with the entry
            if not os.path.exists(env_path):
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(f"{key}={value}\n")
                return

            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            found = False
            for i, ln in enumerate(lines):
                if ln.strip().startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    found = True
                    break

            if not found:
                # ensure newline separation
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] = lines[-1] + "\n"
                lines.append(f"{key}={value}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            logging.getLogger(__name__).debug(
                "Failed to persist .env var %s: %s", key, e
            )

    def _update_run_button_state(self, *args):
        """Enable Run Inference button only when a model is selected and an image is uploaded.

        This method is intentionally tolerant: it looks for common run button
        object names and uses the modelComboBox mapping to determine whether a
        workflow id is selected.
        """
        try:
            run_btn = (
                getattr(self, "imageInferenceButton_2", None)
                or getattr(self, "imageInferenceButton", None)
                or getattr(self, "runImgInferenceButton_2", None)
                or getattr(self, "runImgInferenceButton", None)
                or self._find_widget("imageInferenceButton")
                or self._find_widget("runImgInferenceButton")
            )
            if run_btn is None:
                return

            has_image = bool(getattr(self, "_uploaded_image_path", None))

            # Determine if a workflow is selected from the model combo
            selected_wf = None
            try:
                mcb = self._find_widget("modelComboBox")
                if mcb is not None:
                    idx = mcb.currentIndex()
                    selected_wf = mcb.itemData(idx)
            except Exception:
                selected_wf = None

            run_btn.setEnabled(bool(has_image and selected_wf))
        except Exception:
            pass

    # --- Inference integration -------------------------------------------------
    class _InferenceWorker(QObject):
        """Runs an InferencePipeline in a background thread and emits frames.

        Signals:
            frame_ready: emits a QImage to be shown in the UI
            prediction: emits the raw prediction dict for logging/processing
            error: emits a traceback string when exceptions occur in the worker
        """

        frame_ready = pyqtSignal(QImage)
        prediction = pyqtSignal(object)
        finished = pyqtSignal()
        error = pyqtSignal(str)

        def __init__(self, api_key, workspace, workflow, video_reference, max_fps=30):
            super().__init__()
            self.api_key = api_key
            self.workspace = workspace
            self.workflow = workflow
            self.video_reference = video_reference
            self.max_fps = max_fps
            self._pipeline = None
            self._stopping = False

        def _on_prediction(self, result, video_frame=None):
            try:
                # Try to extract polygon points from any instance segmentation masks
                polygons = None
                try:
                    import numpy as _np

                    preds_obj = None
                    if isinstance(result, dict):
                        preds_obj = result.get("predictions")
                    else:
                        preds_obj = getattr(result, "predictions", None)

                    mask_arr = None
                    if preds_obj is not None:
                        # support dict-like or object with `.mask`
                        if isinstance(preds_obj, dict):
                            mask_arr = preds_obj.get("mask")
                        else:
                            mask_arr = getattr(preds_obj, "mask", None)

                    if isinstance(mask_arr, _np.ndarray):
                        polygons = []
                        # mask_arr expected shape (N, H, W)
                        for mi in range(mask_arr.shape[0]):
                            m = mask_arr[mi].astype(_np.uint8) * 255
                            try:
                                contours, _ = cv2.findContours(
                                    m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                                )
                            except Exception:
                                contours = []
                            item_polys = []
                            for c in contours:
                                if c is None or c.shape[0] < 3:
                                    continue
                                eps = 0.01 * cv2.arcLength(c, True)
                                approx = cv2.approxPolyDP(c, eps, True)
                                pts = [(int(p[0][0]), int(p[0][1])) for p in approx]
                                if pts:
                                    item_polys.append(pts)
                            polygons.append(item_polys)
                except Exception:
                    polygons = None

                # Attach polygons to the result if possible so callers can inspect points
                try:
                    if polygons is not None:
                        if isinstance(result, dict):
                            result["polygons"] = polygons
                        else:
                            try:
                                setattr(result, "polygons", polygons)
                            except Exception:
                                pass
                except Exception:
                    pass

                # Emit raw prediction for any additional handling
                self.prediction.emit(result)

                # If workflow provided an image, try to convert and emit
                img_obj = None
                if isinstance(result, dict) and result.get("output_image"):
                    img_obj = result["output_image"]

                if img_obj is not None:
                    # Many workflows expose `.numpy_image` or `.to_numpy()`
                    arr = None
                    if hasattr(img_obj, "numpy_image"):
                        arr = getattr(img_obj, "numpy_image")
                    elif hasattr(img_obj, "to_numpy"):
                        arr = img_obj.to_numpy()
                    elif hasattr(img_obj, "numpy"):
                        try:
                            arr = img_obj.numpy()
                        except Exception:
                            arr = None

                    if arr is not None:
                        try:
                            # Ensure we have a HxWxC numpy array
                            import numpy as _np

                            if isinstance(arr, _np.ndarray):
                                # If OpenCV-style BGR convert to RGB; try to detect
                                if arr.ndim == 3 and arr.shape[2] == 3:
                                    try:
                                        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                                        qimg = QImage(
                                            rgb.data,
                                            rgb.shape[1],
                                            rgb.shape[0],
                                            rgb.strides[0],
                                            QImage.Format_RGB888,
                                        )
                                    except Exception:
                                        # Fallback to treating array as already RGB
                                        qimg = QImage(
                                            arr.data,
                                            arr.shape[1],
                                            arr.shape[0],
                                            arr.strides[0],
                                            QImage.Format_RGB888,
                                        )
                                    # Ensure the QImage owns its buffer to avoid flicker
                                    try:
                                        qimg = qimg.copy()
                                    except Exception:
                                        pass
                                    self.frame_ready.emit(qimg)
                                else:
                                    # Fallback: try to construct from bytes
                                    try:
                                        data = arr.tobytes()
                                        qimg = QImage(
                                            data,
                                            arr.shape[1],
                                            arr.shape[0],
                                            QImage.Format_Indexed8,
                                        )
                                        try:
                                            qimg = qimg.copy()
                                        except Exception:
                                            pass
                                        self.frame_ready.emit(qimg)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
            except Exception:
                pass

        def run(self):
            # Lazy import to provide clearer error messages
            try:
                from inference import InferencePipeline
            except Exception:
                # No inference library available; report error back
                import traceback

                tb = traceback.format_exc()
                try:
                    self.error.emit(tb)
                except Exception:
                    pass
                return

            try:
                self._pipeline = InferencePipeline.init_with_workflow(
                    api_key=self.api_key,
                    workspace_name=self.workspace,
                    workflow_id=self.workflow,
                    video_reference=self.video_reference,
                    max_fps=self.max_fps,
                    on_prediction=self._on_prediction,
                )
                self._pipeline.start()
                # Wait until pipeline stops; pipeline.join() blocks until finish
                try:
                    self._pipeline.join()
                except Exception:
                    pass
            except Exception:
                import traceback

                tb = traceback.format_exc()
                try:
                    self.error.emit(tb)
                except Exception:
                    pass
            finally:
                # Notify listeners that run() has finished (pipeline stopped or error)
                try:
                    self.finished.emit()
                except Exception:
                    pass

        @pyqtSlot()
        def stop(self):
            self._stopping = True
            try:
                if self._pipeline is not None and hasattr(self._pipeline, "stop"):
                    try:
                        self._pipeline.stop()
                    except Exception:
                        pass
            except Exception:
                pass

    def _toggle_live_inference(self):
        """Start/stop the live inference pipeline when the button is toggled."""
        try:
            btn = getattr(self, "liveInferenceButton", None)
            if btn is None:
                return

            # If already running, stop
            if self._inference_thread is not None:
                # Request the worker to stop inside its own thread via queued invocation
                try:
                    QMetaObject.invokeMethod(
                        self._inference_worker, "stop", Qt.QueuedConnection
                    )
                except Exception:
                    try:
                        # fallback: call directly
                        self._inference_worker.stop()
                    except Exception:
                        pass

                try:
                    try:
                        btn.setText("Live Inference: STOPPING...")
                    except Exception:
                        pass
                    # Wait for the thread to finish; give it a few seconds
                    finished = self._inference_thread.wait(5000)
                    if not finished:
                        # try polite quit, then as last resort terminate
                        try:
                            self._inference_thread.quit()
                            self._inference_thread.wait(2000)
                        except Exception:
                            pass
                    # If still running, terminate (unsafe but avoids hanging)
                    if self._inference_thread.isRunning():
                        try:
                            self._inference_thread.terminate()
                            self._inference_thread.wait(1000)
                        except Exception:
                            pass
                except Exception:
                    pass

                self._inference_thread = None
                self._inference_worker = None
                try:
                    btn.setText("Live Inference: OFF")
                except Exception:
                    pass
                return

            # Start a new pipeline
            # read env for credentials
            api_key = os.environ.get("ROBOFLOW_API_KEY")
            workspace = os.environ.get("ROBOFLOW_WORKSPACE")
            workflow = os.environ.get("ROBOFLOW_WORKFLOW")

            if not api_key or not workspace or not workflow:
                logging.getLogger(__name__).debug(
                    "Missing Roboflow env vars for InferencePipeline"
                )
                try:
                    btn.setText("Live Inference: ERROR")
                except Exception:
                    pass
                return

            # Determine video_reference from selected inputComboBox (try variants)
            vid_ref = 0
            try:
                inp = self._find_widget("inputComboBox")
                if inp is not None:
                    data = inp.currentData()
                    if isinstance(data, int):
                        vid_ref = int(data)
            except Exception:
                pass

            # Create worker and thread
            worker = MainWindow._InferenceWorker(
                api_key, workspace, workflow, vid_ref, max_fps=30
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            # Connect signals
            worker.frame_ready.connect(self._on_inference_image)
            worker.prediction.connect(self._on_prediction_received)
            worker.error.connect(self._on_inference_error)

            # Save and start
            self._inference_worker = worker
            self._inference_thread = thread
            thread.start()
            try:
                # update the correct live button label
                live_btn = self._find_widget("liveInferenceButton")
                if live_btn is not None:
                    live_btn.setText("Live Inference: ON")
            except Exception:
                pass
        except Exception as e:
            logging.getLogger(__name__).debug("_toggle_live_inference error: %s", e)

    def _on_upload_image_clicked(self):
        """Open file dialog, stop live feed, and run inference on chosen image."""
        try:
            # ask for image file
            dlg_parent = self
            file_path, _ = QFileDialog.getOpenFileName(
                dlg_parent,
                "Select image to upload",
                os.path.expanduser("~"),
                "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)",
            )
            if not file_path:
                return

            # stop camera preview if running (switching to image tab)
            try:
                self.stop_camera()
            except Exception:
                pass

            # clear any running inference worker (both video and image)
            try:
                if (
                    self._inference_thread is not None
                    and self._inference_worker is not None
                ):
                    QMetaObject.invokeMethod(
                        self._inference_worker, "stop", Qt.QueuedConnection
                    )
                    self._inference_thread.quit()
                    self._inference_thread.wait(2000)
                self._inference_thread = None
                self._inference_worker = None
            except Exception:
                pass

            try:
                if (
                    self._image_inference_thread is not None
                    and self._image_inference_worker is not None
                ):
                    QMetaObject.invokeMethod(
                        self._image_inference_worker, "stop", Qt.QueuedConnection
                    )
                    self._image_inference_thread.quit()
                    self._image_inference_thread.wait(2000)
                self._image_inference_thread = None
                self._image_inference_worker = None
            except Exception:
                pass

            # store the uploaded path and show it in the image-inference camera view
            try:
                self._uploaded_image_path = file_path
                # Prefer the image tab view (explicit name) so upload shows in
                # the Image tab; otherwise fall back to generic lookup.
                label = (
                    getattr(self, "cameraView_4", None)
                    or self._find_widget("cameraView")
                    or getattr(self, "cameraView", None)
                )
                if label is not None:
                    pix = QPixmap(file_path)
                    if pix.isNull():
                        qimg = QImage(file_path)
                        if not qimg.isNull():
                            pix = QPixmap.fromImage(qimg)
                    if pix and not pix.isNull():
                        try:
                            target_w = label.width() or 658
                            target_h = label.height() or 432
                        except Exception:
                            target_w, target_h = 658, 432
                        scaled = pix.scaled(
                            target_w,
                            target_h,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                        label.setPixmap(scaled)
                        # Update run button state now that an image is available
                        try:
                            self._update_run_button_state()
                        except Exception:
                            pass
            except Exception:
                pass

            # update upload button state
            try:
                upb = (
                    getattr(self, "uploadImgButton_2", None)
                    or getattr(self, "uploadImgButton", None)
                    or self._find_widget("uploadImageButton")
                    or self._find_widget("uploadImgButton")
                )
                if upb is not None:
                    upb.setText("Image Selected")
            except Exception:
                pass

        except Exception as e:
            logging.getLogger(__name__).debug("_on_upload_image_clicked error: %s", e)

    def _on_inference_error(self, tb: str):
        """Handle errors emitted from the inference worker thread."""
        try:
            # Print traceback to console for debugging
            print("Inference worker error:\n", tb)
            logging.getLogger(__name__).error("Inference worker error: %s", tb)
            # Update UI to show error and attempt to stop thread cleanly
            try:
                btn = getattr(self, "liveInferenceButton", None)
                if btn is not None:
                    btn.setText("Live Inference: ERROR")
            except Exception:
                pass

            # Try to stop/cleanup like a normal stop
            try:
                if (
                    self._inference_thread is not None
                    and self._inference_worker is not None
                ):
                    QMetaObject.invokeMethod(
                        self._inference_worker, "stop", Qt.QueuedConnection
                    )
                    self._inference_thread.quit()
                    self._inference_thread.wait(2000)
            except Exception:
                pass
            finally:
                self._inference_thread = None
                self._inference_worker = None
        except Exception:
            pass

    def _freeze_video_inference(self):
        """Stop live inference but keep the last rendered image in the UI."""
        try:
            # Stop the running inference worker if present
            if (
                self._inference_thread is not None
                and self._inference_worker is not None
            ):
                try:
                    QMetaObject.invokeMethod(
                        self._inference_worker, "stop", Qt.QueuedConnection
                    )
                except Exception:
                    try:
                        self._inference_worker.stop()
                    except Exception:
                        pass
                try:
                    self._inference_thread.quit()
                    self._inference_thread.wait(2000)
                except Exception:
                    pass
                # clear references so UI thinks inference is stopped
                self._inference_thread = None
                self._inference_worker = None

            # update live button to show OFF
            try:
                live_btn = self._find_widget("liveInferenceButton")
                if live_btn is not None:
                    live_btn.setText("Live Inference: OFF")
            except Exception:
                pass
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        """Handle switching between Video and Image tabs.

        When the video tab is selected, start the camera automatically using
        the selected input from the video tab input combo. When leaving the
        video tab, stop the camera.
        """
        try:
            # If index 0 -> video tab
            if index == 0:
                # start camera using video tab inputComboBox
                try:
                    inp = self._find_widget("inputComboBox")
                    vid_ref = 0
                    if inp is not None:
                        data = inp.currentData()
                        if isinstance(data, int):
                            vid_ref = int(data)
                    # start camera only if not already started
                    if self._camera_cap is None:
                        self.start_camera(vid_ref)
                except Exception:
                    pass
            else:
                # leaving video tab: stop camera
                try:
                    self.stop_camera()
                except Exception:
                    pass
        except Exception:
            pass

    def _run_image_inference_clicked(self):
        """Start inference on the previously uploaded image (image-inference tab)."""
        try:
            img_path = getattr(self, "_uploaded_image_path", None)
            if not img_path:
                # nothing selected
                return

            # Ensure a model/workflow is selected in the UI before starting
            try:
                mcb = self._find_widget("modelComboBox")
                sel_wf = None
                if mcb is not None:
                    try:
                        sel_wf = mcb.itemData(mcb.currentIndex())
                    except Exception:
                        sel_wf = None
                if not sel_wf:
                    # disable the button and bail out; user must choose a model
                    try:
                        btn = (
                            self._find_widget("imageInferenceButton")
                            or getattr(self, "imageInferenceButton", None)
                            or self._find_widget("runImgInferenceButton")
                            or getattr(self, "runImgInferenceButton", None)
                        )
                        if btn is not None:
                            btn.setEnabled(False)
                    except Exception:
                        pass
                    return
            except Exception:
                pass

            # Read env for credentials
            api_key = os.environ.get("ROBOFLOW_API_KEY")
            workspace = os.environ.get("ROBOFLOW_WORKSPACE")
            workflow = os.environ.get("ROBOFLOW_WORKFLOW")
            if not api_key or not workspace or not workflow:
                logging.getLogger(__name__).debug(
                    "Missing Roboflow env vars for image InferencePipeline"
                )
                try:
                    btn = (
                        self._find_widget("imageInferenceButton")
                        or getattr(self, "imageInferenceButton", None)
                        or self._find_widget("runImgInferenceButton")
                        or getattr(self, "runImgInferenceButton", None)
                    )
                    if btn is not None:
                        btn.setText("Run Error")
                except Exception:
                    pass
                return

            # ensure any previous image worker stopped
            try:
                if (
                    self._image_inference_thread is not None
                    and self._image_inference_worker is not None
                ):
                    QMetaObject.invokeMethod(
                        self._image_inference_worker, "stop", Qt.QueuedConnection
                    )
                    self._image_inference_thread.quit()
                    self._image_inference_thread.wait(2000)
            except Exception:
                pass

            # Create worker and thread for image
            worker = MainWindow._InferenceWorker(
                api_key, workspace, workflow, img_path, max_fps=1
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.frame_ready.connect(self._on_inference_image)
            worker.prediction.connect(self._on_prediction_received)
            worker.error.connect(self._on_inference_error)
            worker.finished.connect(lambda: None)

            self._image_inference_worker = worker
            self._image_inference_thread = thread
            thread.start()

            try:
                btn = (
                    self._find_widget("imageInferenceButton")
                    or getattr(self, "imageInferenceButton", None)
                    or self._find_widget("runImgInferenceButton")
                    or getattr(self, "runImgInferenceButton", None)
                )
                if btn is not None:
                    btn.setText("Running Inference...")
            except Exception:
                pass

            # When thread finishes, reset button text
            def _on_thread_finished():
                try:
                    btn = (
                        self._find_widget("imageInferenceButton")
                        or getattr(self, "imageInferenceButton", None)
                        or self._find_widget("runImgInferenceButton")
                        or getattr(self, "runImgInferenceButton", None)
                    )
                    if btn is not None:
                        btn.setText("Run Inference")
                except Exception:
                    pass
                try:
                    self._image_inference_worker = None
                    self._image_inference_thread = None
                except Exception:
                    pass

            try:
                thread.finished.connect(_on_thread_finished)
            except Exception:
                pass

        except Exception as e:
            logging.getLogger(__name__).debug(
                "_run_image_inference_clicked error: %s", e
            )

    def _on_inference_image(self, qimg: QImage):
        """Receive QImage from worker and display in `cameraView`."""
        try:
            # Prefer the cameraView that corresponds to the visible tab:
            # tab 0 -> video (cameraView_3), tab 1 -> image (cameraView_4)
            label = None
            try:
                tab_idx = (
                    self.tabWidget.currentIndex()
                    if getattr(self, "tabWidget", None) is not None
                    else 0
                )
                if tab_idx == 0:
                    label = getattr(self, "cameraView_3", None)
                else:
                    label = getattr(self, "cameraView_4", None)
            except Exception:
                label = None

            if label is None:
                label = self._find_widget("cameraView") or getattr(
                    self, "cameraView", None
                )

            if label is None or qimg is None:
                return
            pix = QPixmap.fromImage(qimg)
            try:
                target_w = label.width() or 658
                target_h = label.height() or 432
            except Exception:
                target_w, target_h = 658, 432
            scaled = pix.scaled(
                target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            label.setPixmap(scaled)
            label.repaint()
        except Exception:
            pass

    def _on_prediction_received(self, result):
        """Receive the raw prediction object/dict and populate the `inferenceTable`.

        Expected columns: ID, Shape, Confidence.
        The method is defensive: it handles either dict-style results or
        objects with attributes produced by the local `inference` package.
        """
        try:
            # Resolve predictions container
            preds = None
            if isinstance(result, dict):
                preds = result.get("predictions")
            else:
                preds = getattr(result, "predictions", None)

            # Find the table widget (support suffixed names)
            table = self._find_widget("inferenceTable") or getattr(
                self, "inferenceTable", None
            )
            if table is None:
                # nothing to populate
                return

            # Clear existing rows
            try:
                table.setRowCount(0)
            except Exception:
                pass

            # If preds is None, nothing to show
            if preds is None:
                return

            # Try to extract arrays
            confidences = None
            xyxy = None
            data = None
            polygons = None

            try:
                confidences = getattr(preds, "confidence", None)
            except Exception:
                confidences = None

            try:
                xyxy = getattr(preds, "xyxy", None)
            except Exception:
                xyxy = None

            try:
                data = getattr(preds, "data", None)
            except Exception:
                data = None

            # If polygons were attached by the worker, look for them
            try:
                if isinstance(result, dict):
                    polygons = result.get("polygons")
                else:
                    polygons = getattr(result, "polygons", None)
            except Exception:
                polygons = None

            # Number of detections
            n = 0
            try:
                import numpy as _np

                if hasattr(confidences, "__len__") and not isinstance(
                    confidences, float
                ):
                    try:
                        n = int(len(confidences))
                    except Exception:
                        n = 0
                elif xyxy is not None:
                    try:
                        n = int(xyxy.shape[0])
                    except Exception:
                        n = 0
            except Exception:
                n = 0

            # Fallback: if data contains arrays use its length
            if n == 0 and isinstance(data, dict):
                for v in data.values():
                    try:
                        n = int(len(v))
                        break
                    except Exception:
                        continue

            # Populate rows
            for i in range(n):
                try:
                    # ID: prefer detection_id inside data
                    det_id = ""
                    try:
                        if isinstance(data, dict) and "detection_id" in data:
                            det_val = data.get("detection_id")
                            # data values may be numpy arrays
                            try:
                                det_id = str(det_val[i])
                            except Exception:
                                det_id = str(det_val)
                        else:
                            # fallback: use inference id or index
                            if isinstance(data, dict) and "inference_id" in data:
                                try:
                                    det_id = str(data.get("inference_id")[i])
                                except Exception:
                                    det_id = str(i)
                            else:
                                det_id = str(i)
                    except Exception:
                        det_id = str(i)

                    # Shape: show only the simple class name if available
                    shape_str = ""
                    try:
                        cls_name = None
                        # data may be a dict containing 'class_name'
                        if isinstance(data, dict) and "class_name" in data:
                            try:
                                cls_val = data.get("class_name")
                                cls_name = (
                                    str(cls_val[i])
                                    if hasattr(cls_val, "__len__")
                                    else str(cls_val)
                                )
                            except Exception:
                                cls_name = None
                        else:
                            # try attribute on preds
                            try:
                                val = getattr(preds, "class_name", None)
                                if val is not None:
                                    cls_name = (
                                        str(val[i])
                                        if hasattr(val, "__len__")
                                        else str(val)
                                    )
                            except Exception:
                                cls_name = None

                        if cls_name:
                            shape_str = cls_name
                        else:
                            shape_str = ""
                    except Exception:
                        shape_str = ""

                    # Confidence
                    conf_val = ""
                    try:
                        if confidences is not None:
                            try:
                                c = float(confidences[i])
                                conf_val = f"{c:.3f}"
                            except Exception:
                                conf_val = str(confidences[i])
                        else:
                            conf_val = ""
                    except Exception:
                        conf_val = ""

                    # Insert row into table
                    try:
                        row = table.rowCount()
                        table.insertRow(row)
                        # ID
                        from PyQt5.QtWidgets import QTableWidgetItem

                        id_item = QTableWidgetItem(det_id)
                        shape_item = QTableWidgetItem(shape_str)
                        conf_item = QTableWidgetItem(conf_val)
                        table.setItem(row, 0, id_item)
                        table.setItem(row, 1, shape_item)
                        table.setItem(row, 2, conf_item)
                    except Exception:
                        pass
                except Exception:
                    continue
        except Exception:
            pass
