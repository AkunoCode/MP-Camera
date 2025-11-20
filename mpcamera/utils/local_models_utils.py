import torch
import torchvision
from torchvision.models.detection import maskrcnn_resnet50_fpn
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone
import cv2
import numpy as np
import os
import json
import base64
import datetime
import uuid
import warnings

# Suppress the torch load warning for cleaner logs
warnings.filterwarnings("ignore", category=FutureWarning)


class LocalModelInference:
    def __init__(self, model_path, num_classes, device=None):
        """
        Initializes the model by automatically detecting architecture (ResNet50 vs 101).
        """
        self.model_path = model_path
        self.num_classes = num_classes
        self.device = (
            device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        )

        print(f"[INFO] Loading {os.path.basename(model_path)} on {self.device}...")

        # 1. Load Checkpoint
        self.checkpoint = torch.load(self.model_path, map_location=self.device)

        # 2. Extract State Dictionary
        if isinstance(self.checkpoint, dict):
            if "model_state_dict" in self.checkpoint:
                self.state_dict = self.checkpoint["model_state_dict"]
            elif "model" in self.checkpoint:
                self.state_dict = self.checkpoint["model"]
            else:
                self.state_dict = self.checkpoint
        else:
            self.state_dict = self.checkpoint.state_dict()

        # 3. Build & Load Model (Smart Fallback)
        self.model = self._smart_load_model()
        self.model.to(self.device)
        self.model.eval()

    def _smart_load_model(self):
        """
        Attempts to load weights into ResNet50. If keys mismatch, falls back to ResNet101.
        """
        # Attempt 1: ResNet50 (Standard)
        try:
            model = maskrcnn_resnet50_fpn(weights=None, num_classes=self.num_classes)
            model.load_state_dict(self.state_dict, strict=True)
            return model
        except RuntimeError as e:
            if "Unexpected key(s)" in str(e) and "layer3.6" in str(e):
                print(
                    f" -> Architecture Mismatch: {os.path.basename(self.model_path)} requires ResNet101."
                )
            else:
                print(f" -> ResNet50 load failed. Trying ResNet101 fallback.")

        # Attempt 2: ResNet101 (Deeper)
        try:
            backbone = resnet_fpn_backbone("resnet101", weights=None)
            model = torchvision.models.detection.MaskRCNN(
                backbone, num_classes=self.num_classes
            )
            model.load_state_dict(self.state_dict, strict=True)
            print(" -> Successfully loaded as ResNet101.")
            return model
        except RuntimeError as e:
            raise RuntimeError(
                f"Could not load model as ResNet50 OR ResNet101. Error: {e}"
            )

    def predict_json(self, image_path, confidence_threshold=0.5, class_map=None):
        """
        Runs prediction and returns the JSON string directly.
        """
        # 1. Load Image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Image not found: {image_path}")

        h, w, _ = img.shape

        # 2. Preprocess
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_tensor = (
            torch.from_numpy(img_rgb / 255.0).permute(2, 0, 1).float().to(self.device)
        )

        # 3. Inference
        with torch.no_grad():
            prediction = self.model([img_tensor])[0]

        # 4. Filter Results
        keep = prediction["scores"] > confidence_threshold

        boxes = prediction["boxes"][keep].cpu().numpy()
        scores = prediction["scores"][keep].cpu().numpy()
        labels = prediction["labels"][keep].cpu().numpy()
        masks = prediction["masks"][keep].cpu().numpy()

        # 5. Format Predictions List
        formatted_predictions = []

        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes[i]

            # Calculate center x, y, width, height for JSON
            width = float(x2 - x1)
            height = float(y2 - y1)
            cx = float(x1 + (width / 2))
            cy = float(y1 + (height / 2))

            # Process Mask -> Polygon Points
            raw_mask = masks[i, 0]
            binary_mask = (raw_mask > 0.5).astype(np.uint8) * 255

            # Find contours
            contours, _ = cv2.findContours(
                binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            points_list = []
            if contours:
                c = max(contours, key=cv2.contourArea)
                for point in c:
                    px, py = point[0]
                    points_list.append({"x": int(px), "y": int(py)})

            # Determine Class Name
            cls_id = int(labels[i])
            cls_name = (
                class_map.get(cls_id, "Unknown") if class_map else f"Class {cls_id}"
            )

            pred_obj = {
                "width": width,
                "height": height,
                "x": cx,
                "y": cy,
                "confidence": float(scores[i]),
                "class_id": cls_id,
                "points": points_list,
                "class": cls_name,
                "detection_id": str(uuid.uuid4()),
                "parent_id": "image",
            }
            formatted_predictions.append(pred_obj)

        # 6. Construct Final JSON Object
        final_output = {
            "count_objects": len(formatted_predictions),
            "output_image": {
                "type": "base64",
                "value": self._encode_image_base64(image_path),
                "video_metadata": {
                    "video_identifier": "image",
                    "frame_number": 0,
                    "frame_timestamp": datetime.datetime.now().isoformat(),
                    "fps": 30,
                    "measured_fps": None,
                    "comes_from_video_file": None,
                },
            },
            "predictions": {
                "image": {"width": w, "height": h},
                "predictions": formatted_predictions,
            },
        }

        # Return as string
        return json.dumps([final_output], indent=2)

    def _encode_image_base64(self, image_path):
        """Helper to convert image file to base64 string."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")


# --- USAGE EXAMPLE ---
if __name__ == "__main__":
    # Example Class Map
    CLASS_MAP = {
        0: "Background",
        1: "Fragment",
        2: "Pellet",
        3: "Line",
        4: "Sheet",
        5: "Foam",
    }

    # Path to a ResNet101 or ResNet50 model
    MODEL_PATH = "models/PH-optimized-maskrcnn-resnet101.pth"
    IMAGE_PATH = "test_image.jpg"

    try:
        # 1. Init Engine
        inference_engine = LocalModelInference(model_path=MODEL_PATH, num_classes=6)

        # 2. Get JSON Response directly
        json_response = inference_engine.predict_json(
            IMAGE_PATH, confidence_threshold=0.5, class_map=CLASS_MAP
        )

        # 3. Use the response (e.g., return it to an API client)
        print(json_response)

    except Exception as e:
        print(f"Error: {e}")
