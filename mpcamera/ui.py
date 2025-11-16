from PyQt5 import uic
from PyQt5.QtCore import QUrl, QEvent, QObject, QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
import cv2
import os

# Optional: enable remote debugging for Chromium (useful for devtools)
# Port can be opened in a browser: http://localhost:9222
os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9222")

# Load the UI type so the MainWindow class inherits the exact base class
# (e.g. QMainWindow) defined in the .ui file. This avoids nesting a
# QMainWindow inside another window.
ui_path = os.path.join(os.path.dirname(__file__), "SoilSight.ui")
FormClass, BaseClass = uic.loadUiType(ui_path)


class MainWindow(BaseClass, FormClass):
    """Main window that directly uses the QMainWindow from the .ui file.

    This class replaces the `webEnginePlaceholder` widget with an actual
    `QWebEngineView` instance and loads the configured web app URL.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        # Enforce the exact window size from the .ui: 1174x766
        try:
            self.setFixedSize(1174, 766)
        except Exception:
            # fall back to resize if fixed size not available
            self.resize(1174, 766)

        # Ensure the camera view label keeps the intended size (658x432)
        try:
            cam_label = getattr(self, "cameraView", None)
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
            except Exception:
                layout = None

            if layout:
                layout.addWidget(self.webEngineView)
            else:
                self.webEngineView.setGeometry(
                    0, 0, container.width(), container.height()
                )

                class _ResizeFilter(QObject):
                    def __init__(self, view):
                        super().__init__(view)
                        self._view = view

                    def eventFilter(self, obj, event):
                        if event.type() == QEvent.Resize:
                            self._view.setGeometry(0, 0, obj.width(), obj.height())
                        return False

                filter_obj = _ResizeFilter(self.webEngineView)
                container.installEventFilter(filter_obj)

            # Load SoilSight web app
            target_url = QUrl("https://soilsight-one.vercel.app")

            # Connect helpful debugging signals
            try:
                self.webEngineView.loadStarted.connect(
                    lambda: print("WebView: loadStarted")
                )
                self.webEngineView.loadProgress.connect(
                    lambda p: print(f"WebView: loadProgress {p}%")
                )

                def _on_load_finished(ok):
                    print(
                        f"WebView: loadFinished ok={ok} url={self.webEngineView.url().toString()}"
                    )
                    if not ok:
                        # try a simple fallback page to check connectivity
                        print("Loading example.com to check connectivity...")
                        self.webEngineView.setUrl(QUrl("https://example.com"))

                self.webEngineView.loadFinished.connect(_on_load_finished)
                self.webEngineView.urlChanged.connect(
                    lambda u: print(f"WebView: urlChanged {u.toString()}")
                )
            except Exception as e:
                print("Failed to connect load signals:", e)

            self.webEngineView.setUrl(target_url)
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
            label = getattr(self, "cameraView", None)
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
