import torch
import torchvision
from torchvision.models.detection import maskrcnn_resnet50_fpn
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone
import cv2
import numpy as np
import os
import json
import datetime
import uuid
import warnings

# Suppress the torch load warning for cleaner logs
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from ultralytics import YOLO
    import supervision as sv

    _YOLOV11_AVAILABLE = True
except ImportError:
    _YOLOV11_AVAILABLE = False

# Check for RF-DETR-SEG dependencies
try:
    from rfdetr import RFDETRSegPreview
    from PIL import Image

    if not _YOLOV11_AVAILABLE:
        import supervision as sv
    _RFDETR_SEG_AVAILABLE = True
except ImportError:
    _RFDETR_SEG_AVAILABLE = False
# ---------------------------------------------


# --- HELPER FUNCTION TO ALIGN IMGSZ WITH STRIDE 32 (For YOLO) ---
def _adjust_imgsz(size, stride=32):
    """Calculates the nearest multiple of the max stride (32) greater than or equal to the size."""
    return (size + stride - 1) // stride * stride


# ----------------------------------------------------------------


class LocalModelInference:
    def __init__(
        self,
        model_path,
        num_classes,
        confidence_threshold=None,
        iou_threshold=None,
        device=None,
    ):
        """
        Initializes the model by automatically detecting architecture (MaskRCNN, YOLOv11, RF-DETR-SEG).
        """
        self.model_path = model_path
        self.num_classes = num_classes

        try:
            from mpcamera.config import get_settings

            cfg = get_settings()
            confidence_threshold = confidence_threshold or float(
                getattr(cfg.inference, "local_confidence_threshold", 0.5)
            )
            iou_threshold = iou_threshold or float(
                getattr(cfg.inference, "local_iou_threshold", 0.4)
            )
            if device is None:
                pref = getattr(cfg.inference, "device_preference", "auto")
                device = (
                    "cpu"
                    if pref == "cpu"
                    else ("cuda" if torch.cuda.is_available() else "cpu")
                )
        except Exception:
            confidence_threshold = confidence_threshold or 0.5
            iou_threshold = iou_threshold or 0.4
            device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.device = device

        print(f"[INFO] Loading {os.path.basename(model_path)} on {self.device}...")

        # 1. Load Checkpoint for inspection (load on CPU to save VRAM)
        try:
            self.checkpoint = torch.load(self.model_path, map_location="cpu")
        except Exception as e:
            print(
                f"[WARNING] Failed to load checkpoint dictionary directly: {e}. Relying on model path for architecture detection."
            )
            self.checkpoint = {}

        # 2. Determine Model Type
        self.model_type = self._determine_model_type()

        # 3. Build & Load Model (Routing to specific loader)
        self.model = self._smart_load_model()

        # Set to device and eval mode for MaskRCNN (YOLO/DETR handle this internally)
        if self.model_type == "MaskRCNN":
            self.model.to(self.device)
            self.model.eval()

    def _determine_model_type(self):
        """
        Determines the model type, prioritizing RF-DETR-SEG based on name
        to avoid misidentification as YOLO.
        """
        model_path_lower = self.model_path.lower()

        # Heuristic 1: RF-DETR-SEG detection (PRIORITY CHECK)
        if (
            "detr" in model_path_lower
            or "rf" in model_path_lower
            or "seg" in model_path_lower
        ) and _RFDETR_SEG_AVAILABLE:
            print(" -> Detected Model Type: RF-DETR-SEG")
            return "RF-DETR-SEG"

        # Heuristic 2: YOLOv11 detection.
        if model_path_lower.endswith((".pt", ".pth")) and _YOLOV11_AVAILABLE:
            # Check the dictionary structure, if not already identified as RF-DETR
            if isinstance(self.checkpoint, dict) and (
                "model" in self.checkpoint or "names" in self.checkpoint
            ):
                print(" -> Detected Model Type: YOLOv11 (Ultralytics)")
                return "YOLOv11"

        # Default/Fallback: Mask R-CNN
        print(" -> Detected Model Type: MaskRCNN (Default Fallback)")
        return "MaskRCNN"

    def _smart_load_model(self):
        """Builds and loads the model based on the determined architecture."""

        if self.model_type == "YOLOv11":
            if not _YOLOV11_AVAILABLE:
                raise ImportError("YOLOv11 dependency missing.")
            try:
                model = YOLO(self.model_path)
                model.to(self.device)
                return model
            except Exception as e:
                raise RuntimeError(f"Could not load YOLOv11 model: {e}")

        elif self.model_type == "RF-DETR-SEG":
            if not _RFDETR_SEG_AVAILABLE:
                raise ImportError("RF-DETR-SEG dependency missing.")
            try:
                model = RFDETRSegPreview(
                    pretrain_weights=self.model_path,
                    resolution=720,
                    num_classes=self.num_classes,
                    device=self.device,
                )

                print(f" -> Successfully loaded as RF-DETR-SEG on {self.device}.")
                return model
            except Exception as e:
                raise RuntimeError(f"Could not load RF-DETR-SEG model. Error: {e}")

        elif self.model_type == "MaskRCNN":
            # Original Mask R-CNN logic (ResNet50 / ResNet101 fallback)

            # Extract state dictionary from the checkpoint
            if isinstance(self.checkpoint, dict):
                state_dict = self.checkpoint.get(
                    "model_state_dict", self.checkpoint.get("model", self.checkpoint)
                )
            else:
                state_dict = self.checkpoint.state_dict()

            # Attempt 1: ResNet50
            try:
                model = maskrcnn_resnet50_fpn(
                    weights=None, num_classes=self.num_classes
                )
                model.load_state_dict(state_dict, strict=True)
                print(" -> Successfully loaded as MaskRCNN-ResNet50.")
                return model
            except RuntimeError as e:
                # Attempt 2: ResNet101 fallback
                if "layer3.6" in str(e):
                    print(
                        " -> Architecture Mismatch: Requires ResNet101. Trying fallback."
                    )

                backbone = resnet_fpn_backbone("resnet101", weights=None)
                model = torchvision.models.detection.MaskRCNN(
                    backbone, num_classes=self.num_classes
                )
                model.load_state_dict(state_dict, strict=True)
                print(" -> Successfully loaded as MaskRCNN-ResNet101.")
                return model
            except RuntimeError as e:
                raise RuntimeError(
                    f"Could not load model as ResNet50 OR ResNet101. Final Error: {e}"
                )

        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

    # -------------------------------------------------------------
    # PUBLIC PREDICTION INTERFACE
    # -------------------------------------------------------------

    def predict_json(
        self, image_path, confidence_threshold=None, iou_threshold=None, class_map=None
    ):
        """Runs prediction and returns the JSON string directly by routing to the correct method."""

        conf_thresh = (
            confidence_threshold
            if confidence_threshold is not None
            else self.confidence_threshold
        )
        iou_thresh = iou_threshold if iou_threshold is not None else self.iou_threshold

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Image not found: {image_path}")

        h, w, _ = img.shape

        # 2. Route Prediction Logic
        if self.model_type == "YOLOv11":
            formatted_predictions = self._predict_yolov11(
                img, conf_thresh, class_map, iou_thresh
            )
        elif self.model_type == "RF-DETR-SEG":
            formatted_predictions = self._predict_rfdetr_seg(
                img, conf_thresh, class_map
            )
        elif self.model_type == "MaskRCNN":
            formatted_predictions = self._predict_maskrcnn(
                img, conf_thresh, iou_thresh, class_map
            )
        else:
            raise ValueError(f"Unknown model type for prediction: {self.model_type}")

        # 3. Construct Final JSON Object
        final_output = {
            "count_objects": len(formatted_predictions),
            "predictions": {
                "image": {"width": w, "height": h},
                "predictions": formatted_predictions,
            },
        }

        return json.dumps([final_output], indent=2)

    # -------------------------------------------------------------
    # DEDICATED PREDICTION METHODS
    # -------------------------------------------------------------

    def _format_prediction(
        self, bbox_xyxy, score, label, mask_np, class_map, detection_id_prefix="image"
    ):
        """Helper to standardize results formatting (used by all prediction methods)."""
        x1, y1, x2, y2 = bbox_xyxy.astype(int)

        width = float(x2 - x1)
        height = float(y2 - y1)
        cx = float(x1 + (width / 2))
        cy = float(y1 + (height / 2))

        # Process Mask -> Polygon Points
        binary_mask = (mask_np > 0.5).astype(np.uint8) * 255

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

        cls_id = int(label)
        cls_name = class_map.get(cls_id, "Unknown") if class_map else f"Class {cls_id}"

        pred_obj = {
            "width": width,
            "height": height,
            "x": cx,
            "y": cy,
            "confidence": float(score),
            "class_id": cls_id,
            "points": points_list,
            "class": cls_name,
            "detection_id": str(uuid.uuid4()),
            "parent_id": detection_id_prefix,
        }
        return pred_obj

    def _predict_yolov11(self, img_bgr, conf_thresh, class_map, iou_thresh):
        """Inference and post-processing for YOLOv11 using Ultralytics API."""

        H, W, _ = img_bgr.shape
        H_adjusted = _adjust_imgsz(H)
        W_adjusted = _adjust_imgsz(W)
        adjusted_imgsz = [H_adjusted, W_adjusted]

        results = self.model.predict(
            source=img_bgr,
            conf=conf_thresh,
            iou=iou_thresh,
            imgsz=adjusted_imgsz,
            device=self.device,
            verbose=False,
            task="segment",
        )[0]

        detections = sv.Detections.from_ultralytics(results)

        if detections.mask is None:
            print("[WARNING] YOLO model did not return segmentation masks.")
            return []

        formatted_predictions = []
        for bbox_xyxy, mask_np, confidence, class_id in zip(
            detections.xyxy, detections.mask, detections.confidence, detections.class_id
        ):
            pred_obj = self._format_prediction(
                bbox_xyxy=bbox_xyxy,
                score=confidence,
                label=class_id,
                mask_np=mask_np,
                class_map=class_map,
            )
            formatted_predictions.append(pred_obj)

        return formatted_predictions

    def _predict_rfdetr_seg(self, img_bgr, conf_thresh, class_map):
        """Inference and post-processing for RF-DETR-SEG."""

        if not _RFDETR_SEG_AVAILABLE:
            raise RuntimeError(
                "RF-DETR-SEG prediction failed: 'rfdetr' package is not available."
            )

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)

        # 1. Inference: Use the high-level predict method
        results = self.model.predict(img_pil, threshold=conf_thresh)

        # Convert prediction results to supervision.Detections
        detections = results
        if not isinstance(detections, sv.Detections):
            try:
                detections = sv.Detections.from_inference(results)
            except:
                pass

        if detections.mask is None:
            print("[WARNING] RF-DETR-SEG model did not return segmentation masks.")
            return []

        # 2. Extract and Format Results
        formatted_predictions = []
        for bbox_xyxy, mask_np, confidence, class_id in zip(
            detections.xyxy, detections.mask, detections.confidence, detections.class_id
        ):
            pred_obj = self._format_prediction(
                bbox_xyxy=bbox_xyxy,
                score=confidence,
                label=class_id,
                mask_np=mask_np,
                class_map=class_map,
            )
            formatted_predictions.append(pred_obj)

        return formatted_predictions

    def _predict_maskrcnn(self, img_bgr, conf_thresh, iou_thresh, class_map):
        """Original MaskRCNN inference and post-processing logic."""

        h, w, _ = img_bgr.shape

        # 1. Preprocess
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_tensor = (
            torch.from_numpy(img_rgb / 255.0).permute(2, 0, 1).float().to(self.device)
        )

        # 2. Inference
        with torch.no_grad():
            prediction = self.model([img_tensor])[0]

        # 3. Filter Results by Confidence
        conf_keep = prediction["scores"] > conf_thresh

        boxes = prediction["boxes"][conf_keep]
        scores = prediction["scores"][conf_keep]
        labels = prediction["labels"][conf_keep]
        masks = prediction["masks"][conf_keep]

        # 4. Filter Results using NMS
        if len(boxes) > 0:
            nms_keep = torchvision.ops.nms(boxes, scores, iou_thresh)

            boxes = boxes[nms_keep].cpu().numpy()
            scores = scores[nms_keep].cpu().numpy()
            labels = labels[nms_keep].cpu().numpy()
            masks = masks[nms_keep].cpu().numpy()[:, 0, :, :]  # (N, H, W)
        else:
            boxes = boxes.cpu().numpy()
            scores = scores.cpu().numpy()
            labels = labels.cpu().numpy()
            masks = masks.cpu().numpy()[:, 0, :, :]

        # 5. Format Predictions List
        formatted_predictions = []

        for i in range(len(boxes)):
            bbox_xyxy = boxes[i].astype(int)

            pred_obj = self._format_prediction(
                bbox_xyxy=bbox_xyxy,
                score=scores[i],
                label=labels[i],
                mask_np=masks[i],  # shape is (H, W)
                class_map=class_map,
            )
            formatted_predictions.append(pred_obj)

        return formatted_predictions
