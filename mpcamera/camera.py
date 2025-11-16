from PyQt5.QtGui import QImage
import cv2
import logging


def open_camera_device(ref=0, try_backends=None, timeout_ms=3000):
    """Try opening a camera with multiple OpenCV backends.

    Arguments:
      ref: integer index or string device path/URL.
      try_backends: optional list of OpenCV backend constants to try.
      timeout_ms: how long (ms) to wait when checking `isOpened()`.

    Returns:
      (cap, backend_name) on success or (None, error_message) on failure.

    This helper is useful on Windows where different cameras and drivers
    work better with different backends (CAP_DSHOW, CAP_MSMF, FFMPEG, etc.).
    """
    logger = logging.getLogger(__name__)
    if try_backends is None:
        # preferred order for Windows: DirectShow, MSMF, FFMPEG, ANY
        try_backends = [
            (cv2.CAP_DSHOW, "CAP_DSHOW"),
            (cv2.CAP_MSMF, "CAP_MSMF"),
            (cv2.CAP_FFMPEG, "CAP_FFMPEG"),
            (cv2.CAP_ANY, "CAP_ANY"),
        ]

    last_err = []
    for backend, name in try_backends:
        try:
            # For string refs (URLs or device names) pass as-is; for numeric
            # indices ensure int conversion.
            arg = ref
            if isinstance(ref, (int,)):
                cap = cv2.VideoCapture(int(ref), backend)
            else:
                # for strings, attempt to open with backend where supported
                try:
                    cap = cv2.VideoCapture(ref, backend)
                except Exception:
                    # fallback: try without specifying backend
                    cap = cv2.VideoCapture(ref)

            # small wait/check for isOpened
            if cap is None:
                last_err.append(f"{name}: returned None")
                continue
            # If backend reports opened, return it immediately
            if cap.isOpened():
                logger.debug("Opened camera %s with backend %s", ref, name)
                return cap, name

            # otherwise release and log the reason
            try:
                cap.release()
            except Exception:
                pass
            last_err.append(f"{name}: not opened")
        except Exception as e:
            last_err.append(f"{name}: {e}")

    # none succeeded
    err_msg = "; ".join(last_err) or "unknown error"
    return None, err_msg


def qimage_from_bgr_array(arr):
    """Convert an OpenCV BGR numpy array to a QImage (RGB888) and return a copy.

    This helper attempts a safe conversion and ensures the returned QImage
    owns its buffer to avoid flicker or use-after-free when used in GUI.
    """
    try:
        # Expect HxWx3 in BGR
        if arr is None:
            return None
        h, w = arr.shape[0], arr.shape[1]
        if arr.ndim == 3 and arr.shape[2] == 3:
            rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)
            try:
                return qimg.copy()
            except Exception:
                return qimg
        # Grayscale
        if arr.ndim == 2:
            qimg = QImage(arr.data, w, h, arr.strides[0], QImage.Format_Indexed8)
            try:
                return qimg.copy()
            except Exception:
                return qimg
    except Exception:
        return None

    return None
