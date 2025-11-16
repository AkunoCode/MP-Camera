from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QImage
import cv2
import logging


class InferenceWorker(QObject):
    """Runs an InferencePipeline in a background thread and emits frames.

    Signals:
        frame_ready: emits a QImage to be shown in the UI
        prediction: emits the raw prediction dict for logging/processing
        error: emits a traceback string when exceptions occur in the worker
        finished: emitted when run() exits
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
                    if isinstance(preds_obj, dict):
                        mask_arr = preds_obj.get("mask")
                    else:
                        mask_arr = getattr(preds_obj, "mask", None)

                if isinstance(mask_arr, _np.ndarray):
                    polygons = []
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

            # Emit raw prediction
            self.prediction.emit(result)

            # If workflow provided an image, try to convert and emit
            img_obj = None
            if isinstance(result, dict) and result.get("output_image"):
                img_obj = result["output_image"]

            if img_obj is not None:
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
                        import numpy as _np

                        if isinstance(arr, _np.ndarray):
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
                                    qimg = QImage(
                                        arr.data,
                                        arr.shape[1],
                                        arr.shape[0],
                                        arr.strides[0],
                                        QImage.Format_RGB888,
                                    )
                                try:
                                    qimg = qimg.copy()
                                except Exception:
                                    pass
                                self.frame_ready.emit(qimg)
                            else:
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
        try:
            from inference import InferencePipeline
        except Exception:
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
