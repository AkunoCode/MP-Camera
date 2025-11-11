import os
import json
import base64
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QSpinBox,
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from .workers import Worker, VideoWorker
from .utils import find_base64_image

# Optional imports used for image conversion
try:
    import cv2
except Exception:
    cv2 = None

try:
    import numpy as np
except Exception:
    np = None


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Roboflow Inference GUI")
        self.resize(800, 600)

        # Top: config fields
        self.api_url_input = QLineEdit(self)
        self.api_url_input.setPlaceholderText("api_url (leave default if unsure)")
        self.api_url_input.setText(
            os.environ.get("ROBOFLOW_API_URL", "http://localhost:9001")
        )

        self.api_key_input = QLineEdit(self)
        self.api_key_input.setPlaceholderText(
            "api_key (or set ROBOFLOW_API_KEY env var)"
        )
        env_key = os.environ.get("ROBOFLOW_API_KEY", "")
        self.api_key_input.setText(env_key)

        self.workspace_input = QLineEdit(self)
        self.workspace_input.setPlaceholderText("workspace_name (e.g. johann-catalla)")
        self.workspace_input.setText(
            os.environ.get("ROBOFLOW_WORKSPACE", "johann-catalla")
        )

        self.workflow_input = QLineEdit(self)
        self.workflow_input.setPlaceholderText(
            "workflow_id (e.g. detect-count-and-visualize)"
        )
        self.workflow_input.setText(
            os.environ.get("ROBOFLOW_WORKFLOW", "detect-count-and-visualize")
        )

        # Max FPS spinner for live feed control
        self.fps_spin = QSpinBox(self)
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(10)
        self.fps_spin.setSuffix(" fps")

        # Image preview
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(480, 360)
        self.image_label.setStyleSheet("border: 1px solid #888;")

        # Buttons
        self.load_button = QPushButton("Load Image")
        self.load_button.clicked.connect(self.load_image)

        self.run_button = QPushButton("Run Workflow")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.run_workflow)

        self.save_visual_button = QPushButton("Save Visualization")
        self.save_visual_button.setEnabled(False)
        self.save_visual_button.clicked.connect(self.save_visualization)

        # Result text
        self.result_text = QTextEdit(self)
        self.result_text.setReadOnly(True)
        # Mode/status label (shows whether streaming pipeline is used or fallback)
        self.mode_label = QLabel("Mode: idle")
        self.mode_label.setToolTip(
            "Shows whether the streaming InferencePipeline is available or if the app is using per-frame HTTP fallback."
        )
        # Latency / fps display
        self.latency_label = QLabel("Latency: - ms")
        self.fps_label = QLabel("Remote FPS: -")

        # Layouts
        cfg_layout = QHBoxLayout()
        cfg_layout.addWidget(self.api_url_input)
        cfg_layout.addWidget(self.api_key_input)
        cfg_layout.addWidget(self.workspace_input)
        cfg_layout.addWidget(self.workflow_input)
        cfg_layout.addWidget(QLabel("Max FPS:"))
        cfg_layout.addWidget(self.fps_spin)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.load_button)
        btn_layout.addWidget(self.run_button)
        # Live feed toggle button
        self.live_button = QPushButton("Start Live")
        self.live_button.setCheckable(True)
        self.live_button.clicked.connect(self.toggle_live_feed)

        btn_layout.addWidget(self.save_visual_button)
        btn_layout.addWidget(self.live_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(cfg_layout)
        main_layout.addWidget(self.image_label, 0, Qt.AlignCenter)
        # status row
        status_row = QHBoxLayout()
        status_row.addWidget(self.mode_label)
        status_row.addWidget(self.latency_label)
        status_row.addWidget(self.fps_label)
        main_layout.addLayout(status_row)
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(QLabel("Result JSON:"))
        main_layout.addWidget(self.result_text)

        self.setLayout(main_layout)

        # State
        self.current_image_path = None
        self.latest_visual_pixmap = None
        self.worker = None
        self.video_worker = None

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

    def set_preview_pixmap(self, pix: QPixmap):
        scaled = pix.scaled(
            self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def run_workflow(self):
        if not self.current_image_path:
            QMessageBox.warning(self, "No image", "Please load an image first.")
            return

        api_url = self.api_url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        workspace = self.workspace_input.text().strip()
        workflow_id = self.workflow_input.text().strip()

        if not api_key:
            QMessageBox.warning(
                self,
                "Missing API key",
                "Please provide an API key (in the field or via ROBOFLOW_API_KEY env var).",
            )
            return

        # disable UI while running
        self.run_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.result_text.setText("Running workflow...\n")
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
            api_url = (
                self.api_url_input.text().strip() or "https://serverless.roboflow.com"
            )
            api_key = self.api_key_input.text().strip()
            workspace = self.workspace_input.text().strip() or "johann-catalla"
            workflow_id = (
                self.workflow_input.text().strip() or "detect-count-and-visualize"
            )

            if not api_key:
                QMessageBox.warning(
                    self,
                    "Missing API key",
                    "Please provide an API key before starting live feed.",
                )
                self.live_button.setChecked(False)
                return

            self.video_worker = VideoWorker(
                api_url=api_url,
                api_key=api_key,
                workspace=workspace,
                workflow_id=workflow_id,
                video_source=0,
                max_fps=int(self.fps_spin.value()),
            )
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
            self.load_button.setEnabled(False)
            self.run_button.setEnabled(False)
        else:
            if self.video_worker:
                try:
                    self.video_worker.stop()
                except Exception:
                    pass
                try:
                    self.video_worker.wait(2000)
                except TypeError:
                    try:
                        self.video_worker.wait()
                    except Exception:
                        pass
                self.video_worker = None
            self.live_button.setText("Start Live")
            self.mode_label.setText("Mode: idle")
            self.mode_label.setToolTip("")
            self.load_button.setEnabled(True)
            self.run_button.setEnabled(bool(self.current_image_path))

    def on_error(self, message: str):
        self.result_text.append("Error: " + message)
        self.run_button.setEnabled(True)
        self.load_button.setEnabled(True)

    def on_stats(self, latency_seconds: float, measured_fps: float):
        try:
            ms = int(latency_seconds * 1000)
            self.latency_label.setText(f"Latency: {ms} ms")
            self.fps_label.setText(f"Remote FPS: {measured_fps:.1f}")
        except Exception:
            pass

    def on_result(self, result):
        try:
            pretty = json.dumps(result, indent=2)
        except Exception:
            pretty = str(result)
        self.result_text.setPlainText(pretty)

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
