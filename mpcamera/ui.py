import os
import json
import base64
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QAction,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from .workers import Worker, VideoWorker
from .utils import find_base64_image
import tempfile

# Optional imports used for image conversion
try:
    import cv2
except Exception:
    cv2 = None

try:
    import numpy as np
except Exception:
    np = None


class SettingsDialog(QDialog):
    """Modal dialog to edit connection settings (api url, api key, workspace, workflow)."""

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        workspace: str = "",
        workflow: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)

        self.api_url_input = QLineEdit(self)
        self.api_url_input.setPlaceholderText("api_url (leave default if unsure)")
        self.api_url_input.setText(api_url)

        self.api_key_input = QLineEdit(self)
        self.api_key_input.setPlaceholderText(
            "api_key (or set ROBOFLOW_API_KEY env var)"
        )
        self.api_key_input.setText(api_key)

        self.workspace_input = QLineEdit(self)
        self.workspace_input.setPlaceholderText("workspace_name (e.g. johann-catalla)")
        self.workspace_input.setText(workspace)

        self.workflow_input = QLineEdit(self)
        self.workflow_input.setPlaceholderText(
            "workflow_id (e.g. detect-count-and-visualize)"
        )
        self.workflow_input.setText(workflow)

        form = QFormLayout()
        form.addRow("API URL:", self.api_url_input)
        form.addRow("API Key:", self.api_key_input)
        form.addRow("Workspace:", self.workspace_input)
        form.addRow("Workflow:", self.workflow_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Roboflow Inference GUI")
        self.resize(800, 600)

        # Connection/settings stored in memory and editable via the Settings dialog
        self.api_url = os.environ.get("ROBOFLOW_API_URL", "http://localhost:9001")
        self.api_key = os.environ.get("ROBOFLOW_API_KEY", "")
        self.workspace = os.environ.get("ROBOFLOW_WORKSPACE", "johann-catalla")
        self.workflow = os.environ.get(
            "ROBOFLOW_WORKFLOW", "detect-count-and-visualize"
        )

        # Widgets
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(480, 360)
        self.image_label.setStyleSheet("border: 1px solid #888;")

        # Buttons
        self.load_button = QPushButton("Load Image")
        self.load_button.clicked.connect(self.load_image)

        self.capture_button = QPushButton("Capture")
        self.capture_button.setEnabled(False)
        self.capture_button.clicked.connect(self.capture_frame)

        self.run_button = QPushButton("Run Workflow")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.run_workflow)

        self.save_visual_button = QPushButton("Save Visualization")
        self.save_visual_button.setEnabled(False)
        self.save_visual_button.clicked.connect(self.save_visualization)

        # Result widgets (replace previous JSON text box)
        self.total_label = QLabel("Total microplastics: -")
        self.total_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.breakdown_label = QLabel("")
        self.breakdown_label.setWordWrap(True)

        self.detections_table = QTableWidget(0, 3)
        self.detections_table.setHorizontalHeaderLabels(["ID", "Type", "Confidence"])
        self.detections_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.detections_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.detections_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.detections_table.setSelectionMode(QTableWidget.SingleSelection)

        # Status labels
        self.mode_label = QLabel("Mode: idle")
        self.mode_label.setToolTip(
            "Shows whether the streaming InferencePipeline is available or if the app is using per-frame HTTP fallback."
        )
        self.latency_label = QLabel("Latency: - ms")
        self.fps_label = QLabel("Remote FPS: -")

        # Live feed toggle
        self.live_button = QPushButton("Start Live")
        self.live_button.setCheckable(True)
        self.live_button.clicked.connect(self.toggle_live_feed)

        # Menu: move settings to the menu bar
        settings_action = QAction("Connection Settings...", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("Settings")
        settings_menu.addAction(settings_action)

        # Layouts
        cfg_layout = QHBoxLayout()

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.load_button)
        btn_layout.addWidget(self.capture_button)
        btn_layout.addWidget(self.run_button)
        btn_layout.addWidget(self.save_visual_button)
        btn_layout.addWidget(self.live_button)

        # Main layout: left = preview+controls, right = results
        main_layout = QHBoxLayout()

        left_col = QVBoxLayout()
        left_col.addLayout(cfg_layout)
        left_col.addWidget(self.image_label, 0, Qt.AlignCenter)

        status_row = QHBoxLayout()
        status_row.addWidget(self.mode_label)
        status_row.addWidget(self.latency_label)
        status_row.addWidget(self.fps_label)
        left_col.addLayout(status_row)
        left_col.addLayout(btn_layout)

        right_col = QVBoxLayout()
        right_col.addWidget(self.total_label)
        right_col.addWidget(self.breakdown_label)
        right_col.addWidget(self.detections_table)

        main_layout.addLayout(left_col, 2)
        main_layout.addLayout(right_col, 1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # State
        self.current_image_path = None
        self.latest_visual_pixmap = None
        self.latest_frame = None
        self.worker = None
        self.video_worker = None

        # Auto-start live feed
        try:
            self.live_button.setChecked(True)
            self.toggle_live_feed(True)
        except Exception:
            pass

    def open_settings_dialog(self):
        dlg = SettingsDialog(
            api_url=self.api_url,
            api_key=self.api_key,
            workspace=self.workspace,
            workflow=self.workflow,
            parent=self,
        )
        if dlg.exec_() == QDialog.Accepted:
            # apply settings
            self.api_url = dlg.api_url_input.text().strip()
            self.api_key = dlg.api_key_input.text().strip()
            self.workspace = dlg.workspace_input.text().strip()
            self.workflow = dlg.workflow_input.text().strip()

    def get_connection_settings(self):
        """Return (api_url, api_key, workspace, workflow) using stored attributes.

        This centralizes access so run_workflow and live toggle use the hidden settings.
        """
        api_url = self.api_url or "https://serverless.roboflow.com"
        api_key = self.api_key or ""
        workspace = self.workspace or "johann-catalla"
        workflow_id = self.workflow or "detect-count-and-visualize"
        return api_url, api_key, workspace, workflow_id

    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            pix = QPixmap(path)
            if pix.isNull():
                QMessageBox.warning(
                    self, "Invalid image", "Could not load the selected image."
                )
                return
            self.current_image_path = path
            self.set_preview_pixmap(pix)
            self.run_button.setEnabled(True)

    def capture_frame(self):
        """Capture the latest live frame to a temporary file and mark it as current image."""
        if self.latest_frame is None:
            QMessageBox.warning(self, "No frame", "No live frame available to capture.")
            return
        if cv2 is None:
            QMessageBox.warning(
                self, "Missing OpenCV", "OpenCV is required to capture frames."
            )
            return
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                tmp_path = f.name
                # encode as JPEG
                cv2.imencode(
                    ".jpg", self.latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90]
                )[1].tofile(tmp_path)
            self.current_image_path = tmp_path
            pix = QPixmap(tmp_path)
            if not pix.isNull():
                self.set_preview_pixmap(pix)
            self.run_button.setEnabled(True)
        except Exception as e:
            QMessageBox.warning(
                self, "Capture failed", f"Could not save captured frame: {e}"
            )

    def set_preview_pixmap(self, pix: QPixmap):
        scaled = pix.scaled(
            self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def run_workflow(self):
        if not self.current_image_path:
            QMessageBox.warning(self, "No image", "Please load an image first.")
            return
        api_url, api_key, workspace, workflow_id = self.get_connection_settings()

        if not api_key:
            QMessageBox.warning(
                self,
                "Missing API key",
                "Please provide an API key (in Settings or via ROBOFLOW_API_KEY env var).",
            )
            return

        # disable UI while running
        self.run_button.setEnabled(False)
        self.load_button.setEnabled(False)
        # indicate running in results panel
        try:
            self.total_label.setText("Running workflow...")
            self.breakdown_label.setText("")
            self.detections_table.setRowCount(0)
        except Exception:
            pass
        self.mode_label.setText("Mode: one-shot")

        self.worker = Worker(
            api_url=api_url or "https://serverless.roboflow.com",
            api_key=api_key,
            workspace=workspace or "johann-catalla",
            workflow_id=workflow_id or "detect-count-and-visualize",
            image_path=self.current_image_path,
            use_cache=True,
        )
        self.worker.result_ready.connect(self.on_result)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def toggle_live_feed(self, checked: bool):
        # Start or stop the video worker
        if checked:
            api_url, api_key, workspace, workflow_id = self.get_connection_settings()

            # Start the video worker; the worker will emit frames for preview even if api_key is empty.
            self.video_worker = VideoWorker(
                api_url=api_url,
                api_key=api_key,
                workspace=workspace,
                workflow_id=workflow_id,
                video_source=0,
            )
            # preview frames
            try:
                self.video_worker.frame_ready.connect(self.on_frame)
            except Exception:
                pass
            self.video_worker.result_ready.connect(self.on_result)
            self.video_worker.error.connect(self.on_error)
            try:
                self.video_worker.stats_ready.connect(self.on_stats)
            except Exception:
                pass
            self.video_worker.start()

            # update mode label depending on whether pipeline is available
            try:
                from inference import InferencePipeline  # type: ignore

                pipeline_available = True
            except Exception:
                pipeline_available = False

            if pipeline_available:
                self.mode_label.setText("Mode: live (streaming pipeline)")
                self.mode_label.setToolTip(
                    "Using InferencePipeline streaming mode — lower latency expected."
                )
            else:
                self.mode_label.setText("Mode: live (per-frame HTTP — may be slow)")
                self.mode_label.setToolTip(
                    "InferencePipeline not available. Falling back to per-frame HTTP uploads which are slower. Install the streaming SDK that provides `inference.InferencePipeline` to improve latency."
                )

            self.live_button.setText("Stop Live")
            # allow loading an image; running workflow requires a captured/loaded image
            self.load_button.setEnabled(True)
            self.run_button.setEnabled(bool(self.current_image_path))
        else:
            if self.video_worker:
                try:
                    self.video_worker.stop()
                except Exception:
                    pass
                # wait briefly for the worker to stop; if it doesn't, force-terminate
                try:
                    self.video_worker.wait(2000)
                except TypeError:
                    try:
                        self.video_worker.wait(2000)
                    except Exception:
                        pass
                try:
                    if (
                        hasattr(self.video_worker, "isRunning")
                        and self.video_worker.isRunning()
                    ):
                        # Last-resort: terminate the thread
                        try:
                            self.video_worker.terminate()
                        except Exception:
                            pass
                        try:
                            self.video_worker.wait(2000)
                        except Exception:
                            pass
                except Exception:
                    pass
                self.video_worker = None
            self.live_button.setText("Start Live")
            self.mode_label.setText("Mode: idle")
            self.mode_label.setToolTip("")
            self.load_button.setEnabled(True)
            self.run_button.setEnabled(bool(self.current_image_path))

    def on_error(self, message: str):
        # Show error in a dialog and update results header
        try:
            QMessageBox.warning(self, "Error", message)
        except Exception:
            pass
        try:
            self.total_label.setText("Error")
            self.breakdown_label.setText(str(message))
            self.detections_table.setRowCount(0)
        except Exception:
            pass
        self.run_button.setEnabled(True)
        self.load_button.setEnabled(True)

    def on_stats(self, latency_seconds: float, measured_fps: float):
        try:
            ms = int(latency_seconds * 1000)
            self.latency_label.setText(f"Latency: {ms} ms")
            self.fps_label.setText(f"Remote FPS: {measured_fps:.1f}")
        except Exception:
            pass

    def on_frame(self, frame):
        """Receive a BGR numpy frame from the VideoWorker and update preview."""
        try:
            if frame is None:
                return
            self.latest_frame = frame
            # convert BGR -> RGB
            try:
                rgb = (
                    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    if cv2 is not None
                    else frame[..., ::-1]
                )
            except Exception:
                rgb = frame[..., ::-1]

            h, w = rgb.shape[:2]
            bytes_per_line = 3 * w
            from PyQt5.QtGui import QImage

            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            self.set_preview_pixmap(pix)
            # enable capture
            self.capture_button.setEnabled(True)
        except Exception:
            pass

    def on_result(self, result):
        # Build a human-friendly summary instead of raw JSON when possible.
        summary_lines = []

        # Helper to normalize numpy/array-like to python list
        def to_pylist(x):
            if x is None:
                return None
            try:
                return list(x.tolist())
            except Exception:
                try:
                    return list(x)
                except Exception:
                    return [x]

        detections = []  # list of tuples (id, class_name, confidence)
        counts_by_type = {}
        total_count = None

        try:
            # Strategy A: predictions is an object with .data dict and .confidence arrays
            preds = None
            if isinstance(result, dict) and "predictions" in result:
                preds = result.get("predictions")

            if isinstance(result, dict) and "count_objects" in result:
                try:
                    total_count = int(result.get("count_objects"))
                except Exception:
                    total_count = None

            parsed = False

            if preds is not None:
                # If preds is a sequence (list of items), handle each
                if isinstance(preds, (list, tuple)):
                    for p in preds:
                        # p might be a dict-like or object with attributes
                        try:
                            if isinstance(p, dict):
                                cid = p.get("detection_id") or p.get("id")
                                cname = p.get("class_name") or p.get("label")
                                conf_val = None
                                try:
                                    conf_val = (
                                        float(p.get("confidence"))
                                        if p.get("confidence") is not None
                                        else None
                                    )
                                except Exception:
                                    conf_val = None
                            else:
                                # object with attributes
                                data = getattr(p, "data", {}) or {}
                                cname = None
                                cid = None
                                conf_val = None
                                if isinstance(data, dict):
                                    cname = data.get("class_name")
                                    cid = data.get("detection_id")
                                try:
                                    if cname is None and hasattr(p, "class_name"):
                                        cname = getattr(p, "class_name")
                                except Exception:
                                    pass
                                try:
                                    if cid is None and hasattr(p, "detection_id"):
                                        cid = getattr(p, "detection_id")
                                except Exception:
                                    pass
                                try:
                                    if hasattr(p, "confidence"):
                                        conf_val = float(getattr(p, "confidence"))
                                except Exception:
                                    conf_val = None

                            # normalize
                            if (
                                isinstance(
                                    cname,
                                    (
                                        list,
                                        tuple,
                                    ),
                                )
                                and len(cname) > 0
                            ):
                                cname = cname[0]
                            if (
                                isinstance(
                                    cid,
                                    (
                                        list,
                                        tuple,
                                    ),
                                )
                                and len(cid) > 0
                            ):
                                cid = cid[0]

                            cname = str(cname) if cname is not None else None
                            cid = str(cid) if cid is not None else None

                            if conf_val is not None:
                                try:
                                    conf_val = float(conf_val)
                                except Exception:
                                    conf_val = None

                            if cname:
                                counts_by_type[cname] = counts_by_type.get(cname, 0) + 1
                            detections.append((cid, cname, conf_val))
                        except Exception:
                            continue
                    parsed = True
                else:
                    # preds is a Detections-like object with .data and .confidence arrays
                    try:
                        data = getattr(preds, "data", {}) or {}

                        # Direct-index branch for supervision.Detections-like structures
                        if isinstance(data, dict) and (
                            "class_name" in data and "detection_id" in data
                        ):
                            class_arr = data.get("class_name")
                            id_arr = data.get("detection_id")
                            # confidences may be on the preds object or in data
                            conf_arr = None
                            if hasattr(preds, "confidence"):
                                try:
                                    conf_arr = getattr(preds, "confidence")
                                except Exception:
                                    conf_arr = None
                            elif data.get("confidence") is not None:
                                conf_arr = data.get("confidence")

                            # determine number of detections
                            try:
                                n = len(class_arr)
                            except Exception:
                                # try to convert to list then measure
                                try:
                                    n = len(list(class_arr))
                                except Exception:
                                    n = 0

                            for i in range(n):
                                try:
                                    cname = class_arr[i]
                                except Exception:
                                    cname = None
                                try:
                                    cid = id_arr[i]
                                except Exception:
                                    cid = None
                                conf_val = None
                                try:
                                    if conf_arr is not None:
                                        conf_val = float(conf_arr[i])
                                except Exception:
                                    try:
                                        conf_val = (
                                            float(conf_arr)
                                            if conf_arr is not None
                                            else None
                                        )
                                    except Exception:
                                        conf_val = None

                                cname = str(cname) if cname is not None else None
                                cid = str(cid) if cid is not None else None
                                if cname:
                                    counts_by_type[cname] = (
                                        counts_by_type.get(cname, 0) + 1
                                    )
                                detections.append((cid, cname, conf_val))

                            parsed = True
                        else:
                            # Fallback to generic conversion if structure differs
                            class_names = data.get("class_name") or data.get(
                                "class_names"
                            )
                            detection_ids = data.get("detection_id") or data.get(
                                "detection_ids"
                            )
                            confidences = None
                            if hasattr(preds, "confidence"):
                                confidences = getattr(preds, "confidence")
                            elif (
                                isinstance(data, dict)
                                and data.get("confidence") is not None
                            ):
                                confidences = data.get("confidence")

                            class_names = to_pylist(class_names)
                            detection_ids = to_pylist(detection_ids)
                            confidences = to_pylist(confidences)

                            length = 0
                            for arr in (class_names, detection_ids, confidences):
                                if arr is not None:
                                    length = max(length, len(arr))

                            for i in range(length):
                                cid = (
                                    detection_ids[i]
                                    if detection_ids and i < len(detection_ids)
                                    else None
                                )
                                cname = (
                                    class_names[i]
                                    if class_names and i < len(class_names)
                                    else None
                                )
                                conf = (
                                    confidences[i]
                                    if confidences and i < len(confidences)
                                    else None
                                )
                                if cname is not None:
                                    cname = str(cname)
                                if cid is not None:
                                    cid = str(cid)
                                try:
                                    conf_val = float(conf) if conf is not None else None
                                except Exception:
                                    conf_val = None
                                if cname:
                                    counts_by_type[cname] = (
                                        counts_by_type.get(cname, 0) + 1
                                    )
                                detections.append((cid, cname, conf_val))
                            parsed = True
                    except Exception:
                        parsed = False

            # Strategy B: predictions is a plain list of dicts
            if (
                not parsed
                and isinstance(result, dict)
                and "predictions" in result
                and isinstance(result.get("predictions"), list)
            ):
                try:
                    for p in result.get("predictions"):
                        cid = p.get("detection_id") or p.get("id")
                        cname = p.get("class_name") or p.get("label")
                        conf_val = None
                        try:
                            conf_val = (
                                float(p.get("confidence"))
                                if p.get("confidence") is not None
                                else None
                            )
                        except Exception:
                            conf_val = None
                        if cname:
                            counts_by_type[cname] = counts_by_type.get(cname, 0) + 1
                        detections.append((cid, cname, conf_val))
                    parsed = True
                except Exception:
                    parsed = False

            # Strategy C: try to find top-level structures with 'predictions' as string or other
            if not parsed:
                # leave detections empty and fallback to raw JSON display below
                pass

            if total_count is None:
                total_count = (
                    sum(counts_by_type.values()) if counts_by_type else len(detections)
                )

        except Exception:
            # parsing error: fall back to raw JSON
            try:
                summary_lines = [json.dumps(result, indent=2)]
            except Exception:
                summary_lines = [str(result)]

        # Populate the UI result widgets instead of a text box
        try:
            # If we have detections/counts, show structured view
            if detections or counts_by_type:
                self.total_label.setText(f"Total microplastics: {total_count}")
                if counts_by_type:
                    lines = [
                        f"{t}: {c}"
                        for t, c in sorted(counts_by_type.items(), key=lambda x: -x[1])
                    ]
                    self.breakdown_label.setText("; ".join(lines))
                else:
                    self.breakdown_label.setText("")

                # populate table
                self.detections_table.setRowCount(len(detections))
                for row, (cid, cname, conf_val) in enumerate(detections):
                    id_item = QTableWidgetItem((cid or "-")[:128])
                    type_item = QTableWidgetItem(cname or "-")
                    conf_str = f"{conf_val:.2f}" if conf_val is not None else "-"
                    conf_item = QTableWidgetItem(conf_str)
                    self.detections_table.setItem(row, 0, id_item)
                    self.detections_table.setItem(row, 1, type_item)
                    self.detections_table.setItem(row, 2, conf_item)
            else:
                # fallback: show raw JSON/text in breakdown label
                # Add debug logging to help diagnose unexpected prediction shapes
                try:
                    if (
                        (not detections)
                        and isinstance(result, dict)
                        and "predictions" in result
                    ):
                        preds = result.get("predictions")
                        try:
                            print("DEBUG on_result: parsed=", parsed)
                            print("DEBUG on_result: type(predictions)=", type(preds))
                            # short reprs to avoid massive logs
                            try:
                                rpred = repr(preds)
                                print(
                                    "DEBUG on_result: repr(predictions)[:1000]=",
                                    rpred[:1000],
                                )
                            except Exception:
                                pass
                            try:
                                pdata = getattr(preds, "data", None)
                                print(
                                    "DEBUG on_result: getattr(predictions, 'data') type=",
                                    type(pdata),
                                    " repr[:1000]=",
                                    repr(pdata)[:1000],
                                )
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    self.total_label.setText("Result")
                    self.breakdown_label.setText(
                        summary_lines[0] if summary_lines else ""
                    )
                    self.detections_table.setRowCount(0)
                except Exception:
                    pass
        except Exception:
            try:
                # Last-resort fallback: show raw JSON string in breakdown
                self.total_label.setText("Result")
                self.breakdown_label.setText(
                    json.dumps(result) if isinstance(result, dict) else str(result)
                )
                self.detections_table.setRowCount(0)
            except Exception:
                pass

        # If the pipeline returned an object with a numpy image, convert and show
        try:
            if isinstance(result, dict) and "output_image" in result:
                out = result.get("output_image")
                if hasattr(out, "numpy_image"):
                    arr = out.numpy_image
                    if arr is not None:
                        try:
                            if np is not None and arr.ndim == 3 and arr.shape[2] == 3:
                                rgb = (
                                    cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                                    if cv2 is not None
                                    else arr[..., ::-1]
                                )
                                h, w = rgb.shape[:2]
                                bytes_per_line = 3 * w
                                from PyQt5.QtGui import QImage

                                qimg = QImage(
                                    rgb.data, w, h, bytes_per_line, QImage.Format_RGB888
                                )
                                pix = QPixmap.fromImage(qimg)
                                self.latest_visual_pixmap = pix
                                self.set_preview_pixmap(pix)
                                self.save_visual_button.setEnabled(True)
                        except Exception:
                            pass
        except Exception:
            pass

        # Try to find a base64 visualization image in the result
        b64 = find_base64_image(result)
        if b64:
            try:
                data = base64.b64decode(b64)
                pix = QPixmap()
                if pix.loadFromData(data):
                    self.latest_visual_pixmap = pix
                    self.set_preview_pixmap(pix)
                    self.save_visual_button.setEnabled(True)
            except Exception:
                pass

        # Re-enable UI
        self.run_button.setEnabled(True)
        self.load_button.setEnabled(True)

    def save_visualization(self):
        if not self.latest_visual_pixmap:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save visualization",
            "visualization.png",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)",
        )
        if path:
            self.latest_visual_pixmap.save(path)
