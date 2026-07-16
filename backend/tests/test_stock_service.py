import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base_class import Base
from app.models.detection import Detection
from app.models.item import Item
from app.models.label_mapping import LabelMapping
from app.models.stock_history import StockHistory
from app.services.stock_service import StockService


class StockServiceDebounceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = self.SessionLocal()
        StockService.reset_runtime_state()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        StockService.reset_runtime_state()

    def _create_item_with_mapping(
        self,
        *,
        item_id: str = "ITEM001",
        item_name: str = "可口可乐",
        detection_label: str = "cola",
        threshold: int = 3,
        current_stock: int = 0,
        status: str = "normal",
    ) -> Item:
        item = Item(
            id=item_id,
            name=item_name,
            category="饮料",
            aisle="A1",
            threshold=threshold,
            current_stock=current_stock,
            status=status,
        )
        mapping = LabelMapping(
            detection_label=detection_label,
            item_id=item_id,
        )
        self.db.add(item)
        self.db.add(mapping)
        self.db.commit()
        return item

    def test_unmatched_labels_do_not_mark_previously_seen_item_out(self):
        item = self._create_item_with_mapping(current_stock=5, status="normal")

        StockService.process_detections(
            db=self.db,
            detections=[{"label": "cola", "confidence": 0.91}],
            camera_id="camera_1",
        )
        self.db.refresh(item)

        baseline_stock = item.current_stock
        baseline_status = item.status
        baseline_detections = self.db.query(Detection).count()
        baseline_history = self.db.query(StockHistory).count()

        result = StockService.process_detections(
            db=self.db,
            detections=[{"label": "unknown_label", "confidence": 0.88}],
            camera_id="camera_1",
        )

        self.db.refresh(item)
        self.assertEqual(item.status, baseline_status)
        self.assertEqual(item.current_stock, baseline_stock)
        self.assertEqual(result["updated_items"], [])
        self.assertEqual(result["status_changes"], [])
        self.assertEqual(result["pending_status_updates"], [])
        self.assertEqual(result["unmatched_detection_labels"], ["unknown_label"])
        self.assertEqual(self.db.query(Detection).count(), baseline_detections)
        self.assertEqual(self.db.query(StockHistory).count(), baseline_history)

    def test_empty_frames_require_multiple_confirmations_before_out_of_stock(self):
        item = self._create_item_with_mapping(current_stock=4, status="normal")

        StockService.process_detections(
            db=self.db,
            detections=[{"label": "cola", "confidence": 0.97}] * 4,
            camera_id="camera_1",
        )
        self.db.refresh(item)
        self.assertEqual(item.status, "normal")
        self.assertEqual(item.current_stock, 4)

        for expected_frame in (1, 2):
            result = StockService.process_detections(
                db=self.db,
                detections=[],
                camera_id="camera_1",
            )
            self.db.refresh(item)
            self.assertEqual(item.status, "normal")
            self.assertEqual(item.current_stock, 4)
            self.assertEqual(len(result["pending_status_updates"]), 1)
            self.assertEqual(result["pending_status_updates"][0]["status"], "out")
            self.assertEqual(
                result["pending_status_updates"][0]["frames_seen"],
                expected_frame,
            )

        result = StockService.process_detections(
            db=self.db,
            detections=[],
            camera_id="camera_1",
        )

        self.db.refresh(item)
        self.assertEqual(item.status, "out")
        self.assertEqual(item.current_stock, 0)
        self.assertEqual(len(result["status_changes"]), 1)
        self.assertEqual(result["status_changes"][0]["new_status"], "out")

    def test_low_stock_requires_two_consecutive_frames(self):
        item = self._create_item_with_mapping(current_stock=5, status="normal")

        first_result = StockService.process_detections(
            db=self.db,
            detections=[{"label": "cola", "confidence": 0.92}] * 2,
            camera_id="camera_1",
        )
        self.db.refresh(item)

        self.assertEqual(item.status, "normal")
        self.assertEqual(item.current_stock, 5)
        self.assertEqual(len(first_result["pending_status_updates"]), 1)
        self.assertEqual(first_result["pending_status_updates"][0]["status"], "low")
        self.assertEqual(first_result["pending_status_updates"][0]["frames_seen"], 1)

        second_result = StockService.process_detections(
            db=self.db,
            detections=[{"label": "cola", "confidence": 0.94}] * 2,
            camera_id="camera_1",
        )
        self.db.refresh(item)

        self.assertEqual(item.status, "low")
        self.assertEqual(item.current_stock, 2)
        self.assertEqual(len(second_result["status_changes"]), 1)
        self.assertEqual(second_result["status_changes"][0]["new_status"], "low")

    def test_predicted_count_updates_stock_and_summary_count(self):
        item = self._create_item_with_mapping(
            item_name="Cola",
            threshold=5,
            current_stock=2,
            status="low",
        )

        result = StockService.process_detections(
            db=self.db,
            detections=[
                {
                    "label": "cola",
                    "confidence": 0.91,
                    "predicted_count": 4,
                    "x": 10,
                    "y": 20,
                    "w": 100,
                    "h": 80,
                    "class_id": 20,
                }
            ],
            camera_id="camera_counts",
        )

        self.db.refresh(item)
        detection = self.db.query(Detection).one()

        self.assertEqual(item.current_stock, 4)
        self.assertEqual(item.status, "low")
        self.assertEqual(result["detection_counts"], {"Cola": 4})
        self.assertEqual(detection.detected_count, 4)
        self.assertAlmostEqual(detection.confidence, 0.91)

    def test_multiple_boxes_sum_predicted_counts_and_average_box_confidence(self):
        item = self._create_item_with_mapping(
            item_name="Cola",
            threshold=5,
            current_stock=0,
            status="normal",
        )

        result = StockService.process_detections(
            db=self.db,
            detections=[
                {
                    "label": "cola",
                    "confidence": 0.5,
                    "predicted_count": 3,
                    "x": 10,
                    "y": 20,
                    "w": 100,
                    "h": 80,
                    "class_id": 20,
                },
                {
                    "label": "cola",
                    "confidence": 0.9,
                    "predicted_count": 5,
                    "x": 130,
                    "y": 30,
                    "w": 90,
                    "h": 70,
                    "class_id": 20,
                },
            ],
            camera_id="camera_counts",
        )

        self.db.refresh(item)
        detection = self.db.query(Detection).one()

        self.assertEqual(item.current_stock, 8)
        self.assertEqual(item.status, "normal")
        self.assertEqual(result["detection_counts"], {"Cola": 8})
        self.assertEqual(detection.detected_count, 8)
        self.assertAlmostEqual(detection.confidence, 0.7)

    def test_missing_predicted_count_falls_back_to_one(self):
        item = self._create_item_with_mapping(
            item_name="Cola",
            threshold=5,
            current_stock=0,
            status="normal",
        )

        result = StockService.process_detections(
            db=self.db,
            detections=[
                {"label": "cola", "confidence": 0.8},
                {"label": "cola", "confidence": 0.9, "predicted_count": 4},
            ],
            camera_id="camera_counts",
        )

        self.db.refresh(item)

        self.assertEqual(item.current_stock, 5)
        self.assertEqual(result["detection_counts"], {"Cola": 5})

    def test_detection_boxes_are_persisted_for_applied_summary_detection(self):
        from app.models.detection_box import DetectionBox

        self._create_item_with_mapping(
            item_name="Cola",
            threshold=5,
            current_stock=0,
            status="normal",
        )

        StockService.process_detections(
            db=self.db,
            detections=[
                {
                    "label": "cola",
                    "confidence": 0.5,
                    "predicted_count": 3,
                    "count_model_version": "count-test-v1",
                    "x": 10,
                    "y": 20,
                    "w": 100,
                    "h": 80,
                    "class_id": 20,
                },
                {
                    "label": "cola",
                    "confidence": 0.9,
                    "predicted_count": 5,
                    "count_model_version": "count-test-v1",
                    "x": 130,
                    "y": 30,
                    "w": 90,
                    "h": 70,
                    "class_id": 20,
                },
            ],
            camera_id="camera_counts",
        )

        detection = self.db.query(Detection).one()
        boxes = (
            self.db.query(DetectionBox)
            .filter(DetectionBox.detection_id == detection.id)
            .order_by(DetectionBox.id)
            .all()
        )

        self.assertEqual(detection.detected_count, 8)
        self.assertEqual([box.predicted_count for box in boxes], [3, 5])
        self.assertEqual([box.confidence for box in boxes], [0.5, 0.9])
        self.assertEqual([box.count_model_version for box in boxes], ["count-test-v1", "count-test-v1"])
        self.assertEqual(boxes[0].camera_id, "camera_counts")
        self.assertEqual(boxes[0].class_id, 20)
        self.assertEqual(boxes[0].x, 10)


if __name__ == "__main__":
    unittest.main()
