import cv2
import numpy as np
from ultralytics import YOLO
from pathlib import Path
import logging

from app.core.config import settings
from app.services.count_model_service import count_model_service

logger = logging.getLogger(__name__)

class YOLOv8Service:
    def __init__(self, model_path: str = None):
        """
        Initialize YOLOv8 service with trained model

        Args:
            model_path: Path to trained model. If None, uses models/best.pt
        """
        if model_path is None:
            # Default to trained model
            project_root = Path(__file__).parent.parent.parent.parent
            model_path = project_root / 'models' / 'best.pt'

            # Fallback to pretrained if custom model doesn't exist
            if not model_path.exists():
                logger.warning(f"Custom model not found at {model_path}, using yolov8n.pt")
                model_path = 'yolov8n.pt'

        self.conf_threshold = settings.YOLO_CONF_THRESHOLD
        self.iou_threshold = settings.YOLO_IOU_THRESHOLD

        logger.info(f"Loading YOLOv8 model from {model_path}")
        self.model = YOLO(str(model_path))
        logger.info(
            "YOLOv8 inference thresholds configured: conf=%.2f, iou=%.2f",
            self.conf_threshold,
            self.iou_threshold,
        )
        logger.info("YOLOv8 model loaded successfully")

    def detect(self, image_bytes: bytes):
        """
        Run YOLOv8 inference on image bytes

        Args:
            image_bytes: Image data as bytes

        Returns:
            List of detections: [{x, y, w, h, label, confidence, class_id}]
        """
        try:
            # Decode image
            np_arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if img is None:
                logger.error("Failed to decode image")
                return []

            # Run inference
            results = self.model(
                img,
                verbose=False,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
            )

            # Parse results
            detections = []
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    detection = {
                        "x": float(x1),
                        "y": float(y1),
                        "w": float(x2 - x1),
                        "h": float(y2 - y1),
                        "confidence": float(box.conf[0]),
                        "label": self.model.names[int(box.cls[0])],
                        "class_id": int(box.cls[0])
                    }
                    detection.update(count_model_service.predict_for_detection(img, detection))
                    detections.append(detection)

            logger.info(f"Detected {len(detections)} objects")
            return detections

        except Exception as e:
            logger.error(f"Detection error: {e}")
            return []

# Global service instance
yolov8_service = YOLOv8Service()
