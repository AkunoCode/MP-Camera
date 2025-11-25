import cv2
import traceback
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtMultimedia import QMediaDevices


class CameraWorker(QObject):
    # Signals to talk to the UI
    frame_received = pyqtSignal(object)  # Sends the numpy frame
    error_occurred = pyqtSignal(str)  # Sends error messages

    def __init__(self):
        super().__init__()
        self._vc = None
        self._timer = QTimer()
        self._timer.timeout.connect(self._read_frame)
        self._is_streaming = False

        # Apply frame interval from settings if available (fallback to 33 ms)
        try:
            from mpcamera.config import get_settings

            cfg = get_settings()
            interval = int(getattr(cfg.streaming, "frame_interval_ms", 33))
        except Exception:
            interval = 33
        try:
            self._timer.setInterval(interval)
        except Exception:
            # older PyQt versions might not accept setInterval at construction
            pass

    def get_available_cameras(self):
        """Wraps QMediaDevices to return a friendly list."""
        cameras = QMediaDevices.videoInputs()
        results = []
        for i, cam in enumerate(cameras):
            results.append({"description": cam.description(), "index": i})
        return results

    def start_camera(self, index: int):
        """Handles the complex Sony/OpenCV startup logic."""
        if self._is_streaming:
            self.stop_camera()

        try:
            print(f"[WORKER] Opening Camera Index: {index}")
            # 1. Optionally force DirectShow depending on settings (Windows)
            try:
                from mpcamera.config import get_settings

                cfg = get_settings()
                if getattr(cfg.camera, "force_directshow", True):
                    self._vc = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                else:
                    self._vc = cv2.VideoCapture(index)
            except Exception:
                # fallback: try DirectShow first then default
                self._vc = cv2.VideoCapture(index, cv2.CAP_DSHOW)

            if not self._vc.isOpened():
                self._vc = cv2.VideoCapture(index)

            if not self._vc.isOpened():
                self.error_occurred.emit(f"Could not open Camera Index {index}")
                return

            # 2. Apply capture preferences from settings (resolution, codec)
            try:
                from mpcamera.config import get_settings

                cfg = get_settings()
                w = int(getattr(cfg.camera, "resolution_width", 1920))
                h = int(getattr(cfg.camera, "resolution_height", 1080))
                self._vc.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                self._vc.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                fourcc_code = str(getattr(cfg.camera, "fourcc", "MJPG") or "MJPG")
                fourcc = cv2.VideoWriter_fourcc(*fourcc_code)
                self._vc.set(cv2.CAP_PROP_FOURCC, fourcc)
            except Exception:
                # fallback to previous hardcoded values
                self._vc.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                self._vc.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                self._vc.set(cv2.CAP_PROP_FOURCC, fourcc)

            self._is_streaming = True
            # start timer using interval already applied in __init__
            try:
                self._timer.start()
            except Exception:
                # fallback to explicit ms
                try:
                    self._timer.start(33)
                except Exception:
                    pass

        except Exception as e:
            traceback.print_exc()
            self.error_occurred.emit(str(e))

    def stop_camera(self):
        self._timer.stop()
        self._is_streaming = False
        if self._vc:
            self._vc.release()
        self._vc = None

    def _read_frame(self):
        """Internal slot called by timer."""
        if self._vc and self._is_streaming:
            ret, frame = self._vc.read()
            if ret:
                self.frame_received.emit(frame)
            else:
                # Optional: Handle dropped frames
                pass
