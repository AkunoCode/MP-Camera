import os
import time
import tempfile

# Optional deps
try:
    import cv2
except Exception:
    cv2 = None

try:
    import numpy as np
except Exception:
    np = None

# PyQt thread & signals
from PyQt5.QtCore import QThread, pyqtSignal

try:
    from inference_sdk import InferenceHTTPClient
except Exception:
    InferenceHTTPClient = None

try:
    from inference import InferencePipeline
except Exception:
    InferencePipeline = None


class Worker(QThread):
    """Background thread to run a single inference request."""

    result_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self, api_url, api_key, workspace, workflow_id, image_path, use_cache=True
    ):
        super().__init__()
        self.api_url = api_url
        self.api_key = api_key
        self.workspace = workspace
        self.workflow_id = workflow_id
        self.image_path = image_path
        self.use_cache = use_cache

    def run(self):
        if InferenceHTTPClient is None:
            self.error.emit(
                "inference_sdk package not installed. See README.md to install requirements."
            )
            return

        try:
            client = InferenceHTTPClient(api_url=self.api_url, api_key=self.api_key)
            result = client.run_workflow(
                workspace_name=self.workspace,
                workflow_id=self.workflow_id,
                images={"image": self.image_path},
                use_cache=self.use_cache,
            )
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class VideoWorker(QThread):
    """Background thread that captures webcam frames and sends them to the workflow.

    Uses `InferencePipeline` if available; otherwise falls back to OpenCV +
    per-frame `InferenceHTTPClient` uploads.
    """

    result_ready = pyqtSignal(object)
    error = pyqtSignal(str)
    stats_ready = pyqtSignal(float, float)

    def __init__(
        self, api_url, api_key, workspace, workflow_id, video_source=0, max_fps=10
    ):
        super().__init__()
        self.api_url = api_url
        self.api_key = api_key
        self.workspace = workspace
        self.workflow_id = workflow_id
        self.video_source = video_source
        self.max_fps = max_fps
        self._stop_requested = False
        self.pipeline = None

    def stop(self):
        self._stop_requested = True
        try:
            if self.pipeline is not None and hasattr(self.pipeline, "stop"):
                self.pipeline.stop()
        except Exception:
            pass

    def run(self):
        # Prefer streaming pipeline
        if InferencePipeline is not None:
            try:

                def on_pred(predictions, video_frames=None):
                    try:
                        self.result_ready.emit(predictions)
                    except Exception:
                        pass

                self.pipeline = InferencePipeline.init_with_workflow(
                    api_key=self.api_key,
                    workspace_name=self.workspace,
                    workflow_id=self.workflow_id,
                    video_reference=self.video_source,
                    max_fps=self.max_fps,
                    on_prediction=on_pred,
                )
                self.pipeline.start()
                try:
                    if hasattr(self.pipeline, "join"):
                        self.pipeline.join()
                except Exception:
                    pass
            except Exception as e:
                self.error.emit(f"InferencePipeline error: {e}")
            return

        # Fallback path
        if cv2 is None:
            self.error.emit("Neither InferencePipeline nor OpenCV are available.")
            return

        if InferenceHTTPClient is None:
            self.error.emit(
                "inference_sdk is not installed, required for fallback per-frame inference."
            )
            return

        try:
            client = InferenceHTTPClient(api_url=self.api_url, api_key=self.api_key)
        except Exception as e:
            self.error.emit(f"Failed to create InferenceHTTPClient: {e}")
            return

        cap = cv2.VideoCapture(self.video_source)
        if not cap.isOpened():
            self.error.emit("Could not open video source")
            return

        frame_interval = 1.0 / max(1, self.max_fps)
        last_sent_time = 0.0
        try:
            while not self._stop_requested:
                ret, frame = cap.read()
                if not ret:
                    break

                now = time.time()
                if now - last_sent_time < frame_interval:
                    time.sleep(0.005)
                    continue

                max_width = 640
                h, w = frame.shape[:2]
                if w > max_width:
                    new_h = int(h * (max_width / w))
                    frame = cv2.resize(
                        frame, (max_width, new_h), interpolation=cv2.INTER_AREA
                    )

                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                        tmp_path = f.name
                        cv2.imencode(
                            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60]
                        )[1].tofile(tmp_path)

                    send_t0 = time.time()
                    try:
                        result = client.run_workflow(
                            workspace_name=self.workspace,
                            workflow_id=self.workflow_id,
                            images={"image": tmp_path},
                            use_cache=False,
                        )
                        send_latency = time.time() - send_t0
                        measured_fps = 1.0 / max(send_latency, 1e-6)
                        last_sent_time = time.time()
                        self.stats_ready.emit(send_latency, measured_fps)
                        self.result_ready.emit(result)
                    except Exception as e:
                        self.error.emit(str(e))
                finally:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass

        finally:
            try:
                cap.release()
            except Exception:
                pass
