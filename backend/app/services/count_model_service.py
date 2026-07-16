from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

import numpy as np

from app.core.config import settings

project_root_path = str(settings.PROJECT_ROOT)
if project_root_path not in sys.path:
    sys.path.insert(0, project_root_path)

from count_module import CountPredictor

logger = logging.getLogger(__name__)

COUNT_MODEL_VERSION = "count_mbv3_yoloft_224"


class CountModelService:
    def __init__(
        self,
        model_path: str | Path | None = None,
        device: str | None = None,
        *,
        model_version: str = COUNT_MODEL_VERSION,
    ):
        project_root = settings.PROJECT_ROOT
        self.model_path = Path(model_path) if model_path else project_root / "weights" / "count_best.pt"
        self.device_name = device
        self.model_version = model_version
        self.predictor: CountPredictor | None = None

        self._load_model()

    def _load_model(self) -> None:
        if not self.model_path.exists():
            logger.warning("Count model not found at %s; using per-box count fallback", self.model_path)
            return

        try:
            self.predictor = CountPredictor(
                self.model_path,
                device=self.device_name,
                array_color="BGR",
            )
            logger.info(
                "Count predictor loaded from %s on %s; version=%s",
                self.model_path,
                self.predictor.device,
                self.model_version,
            )
        except Exception as exc:
            logger.error("Failed to load count predictor from %s: %s", self.model_path, exc)
            self.predictor = None

    def predict_for_detection(self, image_bgr: np.ndarray | None, detection: Mapping[str, Any]) -> Dict[str, Any]:
        if self.predictor is None or image_bgr is None:
            return self._fallback()

        try:
            count_detection = self._to_count_detection(detection)
            prediction = self.predictor.predict(image_bgr, [count_detection], batch_size=1)[0]
            predicted_count = self._resolve_count(prediction.get("count"))

            return {
                "predicted_count": predicted_count,
                "count_confidence": None,
                "count_model_version": self.model_version,
            }
        except Exception as exc:
            logger.error("Count inference failed: %s", exc)
            return self._fallback()

    @staticmethod
    def _to_count_detection(detection: Mapping[str, Any]) -> Dict[str, Any]:
        x1 = float(detection.get("x", 0.0))
        y1 = float(detection.get("y", 0.0))
        x2 = x1 + float(detection.get("w", 0.0))
        y2 = y1 + float(detection.get("h", 0.0))

        return {
            "xyxy": [x1, y1, x2, y2],
            "class_id": int(detection.get("class_id", 0)),
            "conf": float(detection.get("confidence", 0.0)),
        }

    @staticmethod
    def _resolve_count(count: Any) -> int:
        try:
            return max(1, int(count))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _fallback() -> Dict[str, Any]:
        return {
            "predicted_count": 1,
            "count_confidence": None,
            "count_model_version": None,
        }


count_model_service = CountModelService()
