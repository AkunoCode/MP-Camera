import cv2
import logging
import traceback
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtMultimedia import QMediaDevices

logger = logging.getLogger(__name__)


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
            logger.debug(f"CameraWorker initialized with frame interval: {interval}ms")
        except Exception as e:
            # older PyQt versions might not accept setInterval at construction
            logger.warning(f"Could not set timer interval: {e}")
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
            logger.debug(f"Camera already streaming; stopping before restarting")
            self.stop_camera()

        try:
            logger.info(f"Starting camera on index {index}")
            # 1. Optionally force DirectShow depending on settings (Windows)
            try:
                from mpcamera.config import get_settings

                cfg = get_settings()
                if getattr(cfg.camera, "force_directshow", True):
                    logger.debug(f"Opening camera {index} with CAP_DSHOW backend")
                    self._vc = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                else:
                    logger.debug(f"Opening camera {index} with default backend")
                    self._vc = cv2.VideoCapture(index)
            except Exception as e:
                # fallback: try DirectShow first then default
                logger.warning(f"Error with DirectShow setup: {e}, falling back to CAP_DSHOW")
                self._vc = cv2.VideoCapture(index, cv2.CAP_DSHOW)

            if not self._vc.isOpened():
                logger.debug(f"Camera {index} not opened with CAP_DSHOW, trying default backend")
                self._vc = cv2.VideoCapture(index)

            if not self._vc.isOpened():
                err_msg = f"Could not open Camera Index {index}"
                logger.error(err_msg)
                self.error_occurred.emit(err_msg)
                return

            logger.info(f"Camera {index} opened successfully")

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
                logger.info(f"Camera {index} configured: {w}x{h}, codec {fourcc_code}")
            except Exception as e:
                # fallback to previous hardcoded values
                logger.warning(f"Error configuring camera: {e}, using fallback settings")
                self._vc.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                self._vc.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                self._vc.set(cv2.CAP_PROP_FOURCC, fourcc)

            self._is_streaming = True
            # start timer using interval already applied in __init__
            try:
                self._timer.start()
                logger.info(f"Camera {index} streaming started")
            except Exception as e:
                # fallback to explicit ms
                logger.warning(f"Error starting timer: {e}, trying with explicit interval")
                try:
                    self._timer.start(33)
                except Exception:
                    pass

        except Exception as e:
            # Ensure device handle is released on any error
            logger.error(f"Failed to start camera: {e}", exc_info=True)
            if self._vc is not None and self._vc.isOpened():
                self._vc.release()
            self._vc = None
            self.error_occurred.emit(str(e))

    def stop_camera(self):
        logger.debug("Stopping camera")
        self._timer.stop()
        self._is_streaming = False
        if self._vc:
            self._vc.release()
        self._vc = None
        logger.debug("Camera stopped")

    def _read_frame(self):
        """Internal slot called by timer."""
        if self._vc and self._is_streaming:
            ret, frame = self._vc.read()
            if ret:
                self.frame_received.emit(frame)
            else:
                # Optional: Handle dropped frames
                pass
