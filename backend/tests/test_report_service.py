import sys
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base_class import Base
from app.models.item import Item
from app.models.label_mapping import LabelMapping
from app.models.stock_history import StockHistory
from app.services.report_category_service import report_category_service
from app.services.report_service import report_service


class ReportServiceStockHistoryTests(unittest.TestCase):
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
        self._seed_items()
        self._seed_stock_history()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _seed_items(self):
        self.db.add_all(
            [
                Item(
                    id="ITEM001",
                    name="可口可乐",
                    category="饮料",
                    aisle="A1",
                    threshold=5,
                    current_stock=6,
                    status="normal",
                ),
                Item(
                    id="ITEM002",
                    name="乐事薯片",
                    category="零食",
                    aisle="B1",
                    threshold=4,
                    current_stock=5,
                    status="normal",
                ),
                Item(
                    id="ITEM003",
                    name="Unknown mapped item",
                    category="Do not use this category",
                    aisle="C1",
                    threshold=2,
                    current_stock=3,
                    status="normal",
                ),
            ]
        )
        self.db.add_all(
            [
                LabelMapping(
                    detection_label="Adult milk powder",
                    item_id="ITEM001",
                ),
                LabelMapping(
                    detection_label="Cake",
                    item_id="ITEM002",
                ),
            ]
        )
        self.db.commit()

    def _add_stock_history(self, item_id: str, stock_level: int, timestamp: datetime):
        self.db.add(
            StockHistory(
                item_id=item_id,
                stock_level=stock_level,
                timestamp=timestamp,
            )
        )

    def _seed_stock_history(self):
        self._add_stock_history("ITEM001", 6, datetime(2026, 4, 11, 9, 0))
        self._add_stock_history("ITEM001", 3, datetime(2026, 4, 11, 10, 0))
        self._add_stock_history("ITEM001", 2, datetime(2026, 4, 11, 11, 0))
        self._add_stock_history("ITEM001", 0, datetime(2026, 4, 11, 12, 0))
        self._add_stock_history("ITEM001", 6, datetime(2026, 4, 11, 13, 0))
        self._add_stock_history("ITEM001", 4, datetime(2026, 4, 12, 8, 0))

        self._add_stock_history("ITEM002", 5, datetime(2026, 4, 11, 10, 30))
        self._add_stock_history("ITEM002", 0, datetime(2026, 4, 11, 11, 30))
        self._add_stock_history("ITEM002", 0, datetime(2026, 4, 12, 9, 0))
        self._add_stock_history("ITEM003", 3, datetime(2026, 4, 11, 8, 0))
        self._add_stock_history("ITEM003", 1, datetime(2026, 4, 11, 9, 30))
        self.db.commit()

    def test_all_93_locount_labels_have_report_category_mapping(self):
        labels_path = BACKEND_DIR.parent / "config" / "locount_93_classes.txt"
        labels = [
            line.strip()
            for line in labels_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        self.assertEqual(len(labels), 93)
        self.assertEqual(
            set(labels),
            set(report_category_service.LABEL_TO_CATEGORY_KEY),
        )
        for label in labels:
            self.assertNotEqual(
                report_category_service.category_key_for_label(label),
                report_category_service.OTHER.key,
            )

    def test_representative_labels_use_confirmed_report_categories(self):
        expected_categories = {
            "Adult milk powder": "food_beverage",
            "Cake": "food_beverage",
            "Baby diapers": "personal_care",
            "Baby Furniture": "maternal_child",
            "Draw bar box": "home_kitchen",
            "Children Socks": "clothing",
            "Badminton": "sports_stationery_toys",
            "Desk lamp": "appliances",
            "Socket": "appliances",
        }

        for label, expected_key in expected_categories.items():
            self.assertEqual(
                report_category_service.category_key_for_label(label),
                expected_key,
            )

    def test_category_breakdown_uses_detection_labels_for_report_categories(self):
        result = report_service.get_category_breakdown(
            db=self.db,
            start_date=datetime(2026, 4, 11, 0, 0),
            end_date=datetime(2026, 4, 13, 0, 0),
            days=2,
        )

        category_keys = [category["key"] for category in result["categories"]]
        self.assertEqual(
            category_keys,
            [
                "food_beverage",
                "personal_care",
                "maternal_child",
                "home_kitchen",
                "clothing",
                "sports_stationery_toys",
                "appliances",
                "other",
            ],
        )
        self.assertEqual(result["rows"][0]["name"], "04/11")
        self.assertEqual(result["rows"][0]["date"], "2026-04-11")
        self.assertEqual(result["rows"][0]["values"]["food_beverage"], 3)
        self.assertEqual(result["rows"][0]["values"]["other"], 1)
        self.assertEqual(result["rows"][1]["values"]["food_beverage"], 1)

    def test_multiple_labels_for_one_item_do_not_duplicate_incidents(self):
        self.db.add(
            LabelMapping(
                detection_label="Biscuits",
                item_id="ITEM001",
            )
        )
        self.db.commit()

        result = report_service.get_category_breakdown(
            db=self.db,
            start_date=datetime(2026, 4, 11, 11, 0),
            end_date=datetime(2026, 4, 12, 0, 0),
            days=1,
        )

        self.assertEqual(result["rows"][0]["values"]["food_beverage"], 2)

    def test_adult_milk_powder_and_cake_out_events_count_as_food_beverage(self):
        result = report_service.get_category_breakdown(
            db=self.db,
            start_date=datetime(2026, 4, 11, 11, 0),
            end_date=datetime(2026, 4, 12, 0, 0),
            days=1,
        )

        self.assertEqual(result["rows"][0]["values"]["food_beverage"], 2)

    def test_category_breakdown_keeps_empty_bucket_values_at_zero(self):
        result = report_service.get_category_breakdown(
            db=self.db,
            start_date=datetime(2026, 4, 13, 0, 0),
            end_date=datetime(2026, 4, 14, 0, 0),
            days=1,
        )

        self.assertTrue(
            all(value == 0 for value in result["rows"][0]["values"].values())
        )

    def test_trend_analysis_counts_worsening_stock_events(self):
        result = report_service.get_trend_analysis(
            db=self.db,
            start_date=datetime(2026, 4, 11, 0, 0),
            end_date=datetime(2026, 4, 13, 0, 0),
            days=2,
        )

        self.assertEqual(
            result,
            [
                {"name": "04/11", "incidents": 4},
                {"name": "04/12", "incidents": 1},
            ],
        )

    def test_out_of_stock_trend_counts_real_out_transitions_per_hour(self):
        result = report_service.get_out_of_stock_trend(
            db=self.db,
            hours=5,
            end_date=datetime(2026, 4, 11, 14, 0),
        )

        self.assertEqual(
            result,
            [
                {"time": "09:00", "outOfStock": 0},
                {"time": "10:00", "outOfStock": 0},
                {"time": "11:00", "outOfStock": 1},
                {"time": "12:00", "outOfStock": 1},
                {"time": "13:00", "outOfStock": 0},
            ],
        )

    def test_recent_incident_count_uses_stock_history_events(self):
        result = report_service.get_recent_incident_count(
            db=self.db,
            hours=1,
            end_date=datetime(2026, 4, 11, 12, 0),
        )

        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
