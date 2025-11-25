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
            # 1. Force DirectShow
            self._vc = cv2.VideoCapture(index, cv2.CAP_DSHOW)

            if not self._vc.isOpened():
                self._vc = cv2.VideoCapture(index)

            if not self._vc.isOpened():
                self.error_occurred.emit(f"Could not open Camera Index {index}")
                return

            # 2. Sony A7C / External Cam specific settings
            self._vc.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self._vc.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            self._vc.set(cv2.CAP_PROP_FOURCC, fourcc)

            self._is_streaming = True
            self._timer.start(33)  # ~30 FPS

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
