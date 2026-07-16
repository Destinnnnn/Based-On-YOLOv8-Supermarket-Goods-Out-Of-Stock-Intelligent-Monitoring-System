import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.count_model_service import CountModelService


class CountModelServiceTests(unittest.TestCase):
    def test_missing_model_returns_per_box_count_fallback(self):
        service = CountModelService(model_path=Path("models") / "missing_count_model.pt")

        result = service.predict_for_detection(
            image_bgr=None,
            detection={"x": 0, "y": 0, "w": 10, "h": 10},
        )

        self.assertEqual(result["predicted_count"], 1)
        self.assertIsNone(result["count_confidence"])
        self.assertIsNone(result["count_model_version"])

    def test_predictor_receives_xyxy_class_and_confidence(self):
        model_path = Path("weights") / "count_best.pt"

        with patch.object(Path, "exists", return_value=True), patch(
            "app.services.count_model_service.CountPredictor",
        ) as predictor_cls:
            predictor = Mock()
            predictor.device = "cpu"
            predictor.predict.return_value = [
                {"xyxy": [10.0, 20.0, 40.0, 60.0], "class_id": 7, "conf": 0.91, "count": 6}
            ]
            predictor_cls.return_value = predictor
            service = CountModelService(model_path=model_path, device="cpu")

        image = np.zeros((100, 120, 3), dtype=np.uint8)
        result = service.predict_for_detection(
            image_bgr=image,
            detection={
                "x": 10,
                "y": 20,
                "w": 30,
                "h": 40,
                "class_id": 7,
                "confidence": 0.91,
            },
        )

        predictor_cls.assert_called_once_with(model_path, device="cpu", array_color="BGR")
        predictor.predict.assert_called_once_with(
            image,
            [{"xyxy": [10.0, 20.0, 40.0, 60.0], "class_id": 7, "conf": 0.91}],
            batch_size=1,
        )
        self.assertEqual(result["predicted_count"], 6)
        self.assertIsNone(result["count_confidence"])
        self.assertEqual(result["count_model_version"], "count_mbv3_yoloft_224")

    def test_predictor_error_returns_fallback(self):
        model_path = Path("weights") / "count_best.pt"

        with patch.object(Path, "exists", return_value=True), patch(
            "app.services.count_model_service.CountPredictor",
        ) as predictor_cls:
            predictor = Mock()
            predictor.device = "cpu"
            predictor.predict.side_effect = RuntimeError("count failed")
            predictor_cls.return_value = predictor
            service = CountModelService(model_path=model_path, device="cpu")

        result = service.predict_for_detection(
            image_bgr=np.zeros((20, 20, 3), dtype=np.uint8),
            detection={"x": 0, "y": 0, "w": 10, "h": 10, "class_id": 1, "confidence": 0.8},
        )

        self.assertEqual(result["predicted_count"], 1)
        self.assertIsNone(result["count_confidence"])
        self.assertIsNone(result["count_model_version"])


if __name__ == "__main__":
    unittest.main()
