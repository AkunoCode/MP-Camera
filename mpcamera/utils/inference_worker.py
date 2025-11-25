import json
import os
import threading
import tempfile
import traceback
from PyQt6.QtCore import QObject, pyqtSignal

# Imports moved from controller
try:
    from mpcamera.services.roboflow import RoboflowClient
except ImportError:
    RoboflowClient = None

try:
    from mpcamera.utils.local_models_utils import LocalModelInference
except ImportError:
    LocalModelInference = None

from mpcamera.utils.inference_utils import parse_result_to_preds


class InferenceWorker(QObject):
    # Signals
    finished = pyqtSignal(list, object)  # (predictions_list, raw_result)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._local_engine = None
        self._current_local_model_path = None

        # Constants
        self.LOCAL_NUM_CLASSES = 6
        self.CLASS_MAP = {
            0: "Background",
            1: "Fragment",
            2: "Pellet",
            3: "Fiber",
            4: "Sheet",
            5: "Foam",
        }

    def run_inference(
        self, image_source, model_data, conf=0.40, iou=0.50, is_pixmap=False
    ):
        """
        Main entry point.
        image_source: str (path) or QPixmap
        model_data: str (path to .pth OR roboflow ID)
        """

        # We handle temp file creation here so the Controller doesn't have to
        def worker():
            temp_path = None
            try:
                # 1. Prepare Image Path
                path_to_infer = image_source

                # If input is a QPixmap, save it to temp
                if is_pixmap:
                    t = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    t.close()
                    image_source.save(t.name, "JPG")
                    path_to_infer = t.name
                    temp_path = t.name  # Mark for deletion

                # 2. Determine Model Type
                is_local = str(model_data).endswith(".pth")
                result = None

                if is_local:
                    if not LocalModelInference:
                        raise ImportError("LocalModelInference utils missing.")

                    # Lazy Load Engine
                    if (
                        self._local_engine is None
                        or self._current_local_model_path != model_data
                    ):
                        print(f"[INFERENCE] Loading Local Model: {model_data}")
                        self._local_engine = LocalModelInference(
                            model_path=model_data, num_classes=self.LOCAL_NUM_CLASSES
                        )
                        self._current_local_model_path = model_data

                    # Predict
                    json_str = self._local_engine.predict_json(
                        path_to_infer,
                        confidence_threshold=conf,
                        iou_threshold=iou,
                        class_map=self.CLASS_MAP,
                    )
                    result = json.loads(json_str)

                elif RoboflowClient:
                    # Cloud
                    client = RoboflowClient.get_default()
                    # Ensure correct workflow is set
                    if client.workflow != model_data:
                        client.workflow = model_data

                    try:
                        result = client.run_workflow(
                            path_to_infer, confidence=conf, iou=iou
                        )
                    except TypeError:
                        result = client.run_workflow(path_to_infer)

                # 3. Parse Results
                preds = parse_result_to_preds(result) or []

                # Emit results
                self.finished.emit(preds, result)

            except Exception as e:
                traceback.print_exc()
                self.error.emit(str(e))

            finally:
                # Cleanup
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

        # Run in background thread
        threading.Thread(target=worker, daemon=True).start()
