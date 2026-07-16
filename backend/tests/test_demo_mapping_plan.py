import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.demo_seed_service import (
    CURATED_ITEMS_BY_LABEL,
    TRANSLATED_ITEM_NAMES_BY_LABEL,
    build_full_demo_seed_catalog,
    load_training_labels,
)


class DemoMappingPlanTests(unittest.TestCase):
    def test_translation_table_covers_all_training_labels(self):
        labels = load_training_labels()
        self.assertEqual(set(TRANSLATED_ITEM_NAMES_BY_LABEL), set(labels))

    def test_all_item_names_are_chinese_display_names(self):
        items, mappings = build_full_demo_seed_catalog()
        item_by_id = {item["id"]: item for item in items}

        for mapping in mappings:
            detection_label = mapping["detection_label"]
            item = item_by_id[mapping["item_id"]]
            self.assertEqual(item["name"], TRANSLATED_ITEM_NAMES_BY_LABEL[detection_label])
            self.assertNotEqual(item["name"], detection_label)

    def test_all_training_labels_have_inventory_items_and_mappings(self):
        labels = load_training_labels()
        items, mappings = build_full_demo_seed_catalog()

        self.assertEqual(len(items), len(labels))
        self.assertEqual(len(mappings), len(labels))

        mapped_labels = [mapping["detection_label"] for mapping in mappings]
        self.assertEqual(mapped_labels, labels)

        item_ids = [item["id"] for item in items]
        self.assertEqual(len(item_ids), len(set(item_ids)))

    def test_curated_labels_keep_direct_chinese_names(self):
        items, mappings = build_full_demo_seed_catalog()
        item_by_id = {item["id"]: item for item in items}
        mapping_by_label = {
            mapping["detection_label"]: mapping["item_id"]
            for mapping in mappings
        }

        for label, expected_item in CURATED_ITEMS_BY_LABEL.items():
            mapped_item_id = mapping_by_label[label]
            item = item_by_id[mapped_item_id]
            self.assertEqual(item["id"], expected_item["id"])
            self.assertEqual(item["name"], expected_item["name"])
            self.assertEqual(item["category"], expected_item["category"])

    def test_sample_labels_are_translated_to_expected_chinese_names(self):
        items, mappings = build_full_demo_seed_catalog()
        item_by_id = {item["id"]: item for item in items}

        expected_names = {
            "Chopsticks": "筷子",
            "Coffee": "咖啡",
            "Adult Diapers": "成人纸尿裤",
            "Potato chips": "薯片",
        }

        for label, expected_name in expected_names.items():
            mapping = next(row for row in mappings if row["detection_label"] == label)
            item = item_by_id[mapping["item_id"]]
            self.assertEqual(item["name"], expected_name)
            continue
            self.assertEqual(item["category"], "自动映射")
            self.assertEqual(item["aisle"], "AUTO")


if __name__ == "__main__":
    unittest.main()
