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
import tempfile
import numpy as _np

from mpcamera.directus.directus import DirectusClient
from mpcamera.helpers import persist_env_var, parse_prediction_to_rows
from mpcamera.inference_worker import InferenceWorker
from mpcamera.camera import qimage_from_bgr_array, open_camera_device

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
        # Last prediction and last displayed image (QImage) for saving
        self._last_prediction = None
        self._last_inference_qimage = None

        # Wire save button and state updates
        try:
            save_btn = getattr(self, "saveInferenceButton", None)
            if save_btn is not None:
                save_btn.clicked.connect(self._save_inference_to_directus)
                # initially disabled until conditions met
                try:
                    save_btn.setEnabled(False)
                except Exception:
                    pass
        except Exception:
            pass

        # connect sample and magnification changes to update save button state
        try:
            sample_cb = getattr(self, "sampleComboBox", None)
            if sample_cb is not None:
                sample_cb.currentIndexChanged.connect(self._update_save_button_state)
        except Exception:
            pass
        try:
            mag_le = getattr(self, "maginficationLineEdit", None)
            if mag_le is not None:
                mag_le.textChanged.connect(self._update_save_button_state)
        except Exception:
            pass

    # Camera control methods
    def start_camera(self, index=0):
        """Start capturing from camera index and display in `cameraView` label."""
        try:
            if self._camera_cap is not None:
                return

            # prefer integer index for cameras; coerce when possible
            ref = index
            try:
                if isinstance(index, str) and index.isdigit():
                    ref = int(index)
            except Exception:
                pass

            cap, backend_info = open_camera_device(ref)
            if cap is None:
                print(f"Unable to open camera {index} — {backend_info}")
                return

            self._camera_cap = cap
            self._camera_timer.start()
            print(f"Camera started (index={index}) using backend {backend_info}")
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
            # Convert OpenCV frame to QImage using helper
            qimg = qimage_from_bgr_array(frame)
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
            # Update runtime env and persist to project .env using helper
            os.environ["ROBOFLOW_WORKFLOW"] = str(wf)
            try:
                persist_env_var("ROBOFLOW_WORKFLOW", str(wf))
            except Exception:
                pass
        except Exception:
            pass

    # `.env` persistence is handled by `mpcamera.helpers.persist_env_var`

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

    def _stop_worker_thread(self, worker, thread, timeout_ms=5000):
        """Attempt to stop a worker moved to a QThread.

        Strategy:
          - request stop via queued call to worker.stop()
          - wait `timeout_ms`
          - if still running, try calling worker._pipeline.stop() if available
          - wait a bit more, then quit/wait, then terminate as last resort
        """
        try:
            if worker is None or thread is None:
                return
            try:
                QMetaObject.invokeMethod(worker, "stop", Qt.QueuedConnection)
            except Exception:
                try:
                    worker.stop()
                except Exception:
                    pass

            # initial wait
            finished = thread.wait(timeout_ms)
            if not finished:
                # try direct pipeline stop if accessible
                try:
                    pl = getattr(worker, "_pipeline", None)
                    if pl is not None and hasattr(pl, "stop"):
                        try:
                            pl.stop()
                        except Exception:
                            pass
                except Exception:
                    pass

                # wait a bit more
                try:
                    finished = thread.wait(int(timeout_ms / 2))
                except Exception:
                    finished = False

                # polite quit
                if not finished:
                    try:
                        thread.quit()
                        thread.wait(2000)
                    except Exception:
                        pass

            # final resort: terminate
            try:
                if thread.isRunning():
                    try:
                        thread.terminate()
                        thread.wait(1000)
                    except Exception:
                        pass
            except Exception:
                pass

        except Exception:
            pass

    # Inference worker extracted to `mpcamera.inference_worker.InferenceWorker`

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
                        # attempt to call pipeline.stop() directly if available
                        try:
                            pl = getattr(self._inference_worker, "_pipeline", None)
                            if pl is not None and hasattr(pl, "stop"):
                                try:
                                    pl.stop()
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # wait a bit more for the thread to exit
                        finished = self._inference_thread.wait(3000)

                        # try polite quit, then as last resort terminate
                        if not finished:
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
            worker = InferenceWorker(api_key, workspace, workflow, vid_ref, max_fps=30)
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
                    self._stop_worker_thread(
                        self._inference_worker, self._inference_thread
                    )
                self._inference_thread = None
                self._inference_worker = None
            except Exception:
                pass

            try:
                if (
                    self._image_inference_thread is not None
                    and self._image_inference_worker is not None
                ):
                    self._stop_worker_thread(
                        self._image_inference_worker, self._image_inference_thread
                    )
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
                    self._stop_worker_thread(
                        self._inference_worker, self._inference_thread
                    )
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
                    self._stop_worker_thread(
                        self._inference_worker, self._inference_thread
                    )
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
                    self._stop_worker_thread(
                        self._image_inference_worker, self._image_inference_thread
                    )
            except Exception:
                pass

            # Create worker and thread for image
            worker = InferenceWorker(api_key, workspace, workflow, img_path, max_fps=1)
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
            # store last displayed image for potential cropping/upload
            try:
                # keep a copy to avoid buffer lifetime issues
                self._last_inference_qimage = qimg.copy()
            except Exception:
                try:
                    self._last_inference_qimage = QImage(qimg)
                except Exception:
                    self._last_inference_qimage = None
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
            # Use helper parser to normalize prediction rows
            table = self._find_widget("inferenceTable") or getattr(
                self, "inferenceTable", None
            )
            if table is None:
                return

            # store last raw prediction for saving later
            try:
                self._last_prediction = result
            except Exception:
                self._last_prediction = None

            # Clear existing rows
            try:
                table.setRowCount(0)
            except Exception:
                pass

            try:
                rows = parse_prediction_to_rows(result)
            except Exception:
                rows = []

            from PyQt5.QtWidgets import QTableWidgetItem
            from PyQt5.QtCore import Qt as _Qt

            for det_id, cls_name, conf_str in rows:
                try:
                    # insert row
                    row = table.rowCount()
                    table.insertRow(row)
                    id_item = QTableWidgetItem(str(det_id))
                    shape_item = QTableWidgetItem(str(cls_name))
                    conf_item = QTableWidgetItem(str(conf_str))
                    # store numeric value for sorting if available
                    try:
                        num = float(conf_str)
                        conf_item.setData(_Qt.UserRole, num)
                    except Exception:
                        conf_item.setData(_Qt.UserRole, None)

                    table.setItem(row, 0, id_item)
                    table.setItem(row, 1, shape_item)
                    table.setItem(row, 2, conf_item)
                except Exception:
                    continue
            # update save button state now that new results exist
            try:
                self._update_save_button_state()
            except Exception:
                pass
        except Exception:
            pass

    def _update_save_button_state(self, *args):
        """Enable save button only when sample selected, magnification provided, and results exist."""
        try:
            save_btn = getattr(self, "saveInferenceButton", None)
            if save_btn is None:
                return

            # sample selected?
            sample_cb = getattr(self, "sampleComboBox", None)
            sample_ok = False
            try:
                if sample_cb is not None:
                    data = sample_cb.currentData()
                    sample_ok = data not in (None, "", 0)
            except Exception:
                sample_ok = False

            # magnification provided?
            mag_le = getattr(self, "maginficationLineEdit", None)
            mag_ok = False
            try:
                if mag_le is not None:
                    mag_ok = bool(str(mag_le.text()).strip())
            except Exception:
                mag_ok = False

            # results exist?
            results_ok = False
            try:
                if self._last_prediction is not None:
                    # raw prediction exists
                    results_ok = True
                else:
                    tbl = getattr(self, "inferenceTable", None)
                    if tbl is not None and tbl.rowCount() > 0:
                        results_ok = True
            except Exception:
                results_ok = False

            save_btn.setEnabled(bool(sample_ok and mag_ok and results_ok))
        except Exception:
            pass

    def _save_inference_to_directus(self):
        """Save current inference detections to Directus `microplastics` collection.

        This will attempt to crop each detection (using polygons if present or
        falling back to bounding boxes), upload the cropped image via
        DirectusClient.upload_file, and create a microplastic item per
        detection using `create_microplastic`.
        """
        try:
            save_btn = getattr(self, "saveInferenceButton", None)
            if save_btn is None:
                return

            # basic guards (sample, magnification, prediction/image)
            sample_cb = getattr(self, "sampleComboBox", None)
            if sample_cb is None:
                return
            sample_id = sample_cb.currentData()
            if sample_id in (None, "", 0):
                return

            mag_le = getattr(self, "maginficationLineEdit", None)
            mag_val = None
            if mag_le is not None:
                mag_val = str(mag_le.text()).strip()
            if not mag_val:
                return

            result = getattr(self, "_last_prediction", None)
            if result is None:
                return

            # Obtain source image (uploaded path has priority)
            src_img = None
            img_path = getattr(self, "_uploaded_image_path", None)
            if img_path and os.path.exists(img_path):
                try:
                    src_img = cv2.imread(img_path)
                except Exception:
                    src_img = None

            # fallback: use last displayed QImage
            if (
                src_img is None
                and getattr(self, "_last_inference_qimage", None) is not None
            ):
                try:
                    q = self._last_inference_qimage
                    q = q.convertToFormat(QImage.Format_RGB888)
                    w = q.width()
                    h = q.height()
                    ptr = q.bits()
                    ptr.setsize(q.byteCount())
                    arr = _np.frombuffer(ptr, _np.uint8).reshape((h, w, 3))
                    # QImage is RGB888, convert to BGR for opencv
                    src_img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                except Exception:
                    src_img = None

            if src_img is None:
                print("No source image available for saving inference")
                return

            # Normalize predictions list
            preds = None
            if isinstance(result, dict):
                preds = result.get("predictions") or []
            else:
                preds = getattr(result, "predictions", []) or []

            if not preds:
                print("No detections found in prediction result")
                return

            client = None
            try:
                client = DirectusClient()
            except Exception as e:
                print("Directus client init failed:", e)
                return

            successes = 0
            # iterate detections
            for idx, pred in enumerate(preds):
                try:
                    # try polygon from result.polygons (worker may have attached)
                    poly = None
                    try:
                        polygons = None
                        if isinstance(result, dict):
                            polygons = result.get("polygons")
                        else:
                            polygons = getattr(result, "polygons", None)
                        if polygons and len(polygons) > idx:
                            # polygons[idx] may be list of item_polys; pick first polygon
                            item_polys = polygons[idx]
                            if item_polys and len(item_polys) > 0:
                                poly = item_polys[0]
                    except Exception:
                        poly = None

                    # fallback: try bounding box keys
                    bbox = None
                    try:
                        if isinstance(pred, dict):
                            # common patterns
                            if (
                                "x_min" in pred
                                and "y_min" in pred
                                and "x_max" in pred
                                and "y_max" in pred
                            ):
                                bbox = (
                                    int(pred["x_min"]),
                                    int(pred["y_min"]),
                                    int(pred["x_max"]),
                                    int(pred["y_max"]),
                                )
                            elif (
                                "x" in pred
                                and "y" in pred
                                and "width" in pred
                                and "height" in pred
                            ):
                                x = int(pred.get("x", 0))
                                y = int(pred.get("y", 0))
                                w = int(pred.get("width", 0))
                                h = int(pred.get("height", 0))
                                bbox = (x, y, x + w, y + h)
                            elif (
                                "bbox" in pred
                                and isinstance(pred.get("bbox"), (list, tuple))
                                and len(pred.get("bbox")) >= 4
                            ):
                                b = pred.get("bbox")
                                bbox = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
                    except Exception:
                        bbox = None

                    # Use polygon to compute bounding box if available
                    if poly and not bbox:
                        xs = [p[0] for p in poly]
                        ys = [p[1] for p in poly]
                        if xs and ys:
                            x0 = max(0, min(xs))
                            y0 = max(0, min(ys))
                            x1 = min(src_img.shape[1] - 1, max(xs))
                            y1 = min(src_img.shape[0] - 1, max(ys))
                            bbox = (x0, y0, x1, y1)

                    if not bbox:
                        # nothing to crop, skip
                        continue

                    x0, y0, x1, y1 = bbox
                    # ensure within image bounds
                    x0 = max(0, min(int(x0), src_img.shape[1] - 1))
                    x1 = max(0, min(int(x1), src_img.shape[1] - 1))
                    y0 = max(0, min(int(y0), src_img.shape[0] - 1))
                    y1 = max(0, min(int(y1), src_img.shape[0] - 1))
                    if x1 <= x0 or y1 <= y0:
                        continue

                    crop = src_img[y0:y1, x0:x1]
                    if crop is None or crop.size == 0:
                        continue

                    # compute a simple color name (blue, red, white, green, grey, yellow, black)
                    try:
                        mean_bgr = _np.mean(_np.reshape(crop, (-1, 3)), axis=0)
                        # convert BGR -> RGB ordering
                        r, g, b = int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0])
                        try:
                            from mpcamera.helpers import simple_color_name

                            color_name = simple_color_name((r, g, b))
                        except Exception:
                            color_name = "grey"
                    except Exception:
                        color_name = ""

                    # get shape/class and confidence using multiple fallbacks
                    shape = ""
                    conf = None
                    try:
                        # 1) Try common keys directly on the prediction dict/object
                        def _try_keys(obj, keys):
                            for k in keys:
                                try:
                                    if isinstance(obj, dict):
                                        if k in obj and obj.get(k) not in (None, ""):
                                            return obj.get(k)
                                    else:
                                        v = getattr(obj, k, None)
                                        if v not in (None, ""):
                                            return v
                                except Exception:
                                    continue
                            return None

                        class_keys = [
                            "class",
                            "class_name",
                            "label",
                            "name",
                            "pred_class",
                            "prediction",
                        ]
                        conf_keys = [
                            "confidence",
                            "score",
                            "probability",
                            "conf",
                            "confidence_level",
                            "confidence_score",
                        ]

                        val = _try_keys(pred, class_keys)
                        if val is not None:
                            shape = str(val)

                        cval = _try_keys(pred, conf_keys)
                        if cval is not None:
                            try:
                                conf = float(cval)
                            except Exception:
                                try:
                                    conf = float(str(cval))
                                except Exception:
                                    conf = None

                        # 2) If still missing, try structured `result['data']` arrays
                        if (not shape or shape == "") or conf is None:
                            try:
                                data = None
                                if isinstance(result, dict):
                                    data = result.get("data")
                                else:
                                    data = getattr(result, "data", None)
                                if isinstance(data, dict):
                                    # class names array
                                    for key in ("class_name", "class", "label", "name"):
                                        if key in data:
                                            try:
                                                arr = data.get(key)
                                                # attempt index access
                                                if hasattr(arr, "__len__"):
                                                    try:
                                                        cand = arr[idx]
                                                        if cand not in (None, ""):
                                                            shape = str(cand)
                                                            break
                                                    except Exception:
                                                        # maybe arr is scalar
                                                        if arr not in (None, ""):
                                                            shape = str(arr)
                                                            break
                                            except Exception:
                                                continue
                                    # confidences array
                                    for key in (
                                        "confidence",
                                        "conf",
                                        "score",
                                        "probability",
                                    ):
                                        if key in data and conf is None:
                                            try:
                                                arr = data.get(key)
                                                if hasattr(arr, "__len__"):
                                                    try:
                                                        cand = float(arr[idx])
                                                        conf = cand
                                                        break
                                                    except Exception:
                                                        continue
                                            except Exception:
                                                continue
                            except Exception:
                                pass

                        # 3) final fallback: use parse_prediction_to_rows if available
                        if (not shape or shape == "") or conf is None:
                            try:
                                rows_map = parse_prediction_to_rows(result)
                                if rows_map and len(rows_map) > idx:
                                    _, cls_name, conf_str = rows_map[idx]
                                    if (not shape or shape == "") and cls_name:
                                        shape = str(cls_name)
                                    if conf is None and conf_str:
                                        try:
                                            conf = float(conf_str)
                                        except Exception:
                                            conf = None
                            except Exception:
                                pass
                    except Exception:
                        shape = ""
                        conf = None

                    # write crop to temp file
                    tf = None
                    try:
                        fd, tmp_path = tempfile.mkstemp(suffix=".png")
                        os.close(fd)
                        # OpenCV expects BGR; crop is already BGR
                        cv2.imwrite(tmp_path, crop)
                        tf = tmp_path
                    except Exception:
                        tf = None

                    if tf is None:
                        continue

                    # upload file to Directus (debugging info included)
                    try:
                        # file exists and size
                        try:
                            sz = os.path.getsize(tf) if tf and os.path.exists(tf) else None
                        except Exception:
                            sz = None
                        print(f"Uploading file {tf!r}, size={sz}")
                        resp = client.upload_file(tf)
                        print("Directus upload response:", resp)
                        # try to extract file id
                        file_id = None
                        if isinstance(resp, dict):
                            # Directus typically returns {'data': {...}}
                            if "data" in resp and isinstance(resp.get("data"), dict):
                                file_id = resp.get("data").get("id")
                            else:
                                # some Directus installs return the created file record directly
                                file_id = resp.get("id") or resp.get("data")
                        else:
                            file_id = None
                        print("Resolved file_id:", file_id)
                    except Exception as e:
                        print("File upload failed:", e)
                        file_id = None

                    # build item payload
                    item = {
                        "sample_source": sample_id,
                        "shape": str(shape) if shape is not None else "",
                        "color": color_name,
                        "confidence_level": float(conf) if conf is not None else None,
                        "magnification": mag_val,
                    }
                    if file_id is not None:
                        item["image"] = file_id

                    # create microplastic record
                    try:
                        create_resp = client.create_microplastic(item)
                        successes += 1
                        print("Saved microplastic:", create_resp)
                    except Exception as e:
                        print("Failed to create microplastic item:", e)

                    # remove temp file
                    try:
                        if tf and os.path.exists(tf):
                            os.remove(tf)
                    except Exception:
                        pass

                except Exception as e:
                    print("Error saving detection:", e)
                    continue

            # feedback: update button text briefly
            try:
                save_btn.setText(f"Saved {successes}")
            except Exception:
                pass

        except Exception as e:
            print("_save_inference_to_directus error:", e)
            try:
                save_btn = getattr(self, "saveInferenceButton", None)
                if save_btn is not None:
                    save_btn.setText("Save Error")
            except Exception:
                pass
