import sys
import unittest
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.v1.endpoints import inventory, settings as settings_endpoint
from app.core.config import settings
from app.db.base_class import Base
from app.db.database import get_db
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.detection_box import DetectionBox
from app.models.item import Item
from app.models.label_mapping import LabelMapping
from app.models.stock_history import StockHistory
from app.models.user import User
from app.services.auth_service import auth_service
from app.services.stock_service import StockService


class ManagementFeatureTests(unittest.TestCase):
    def setUp(self):
        self._original_secret = settings.AUTH_SECRET_KEY
        self._original_presence = settings.STOCK_PRESENCE_CONFIRMATION_FRAMES
        self._original_absence = settings.STOCK_ABSENCE_CONFIRMATION_FRAMES

        settings.AUTH_SECRET_KEY = "test-management-secret-0123456789"
        settings.STOCK_PRESENCE_CONFIRMATION_FRAMES = 2
        settings.STOCK_ABSENCE_CONFIRMATION_FRAMES = 3

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        Base.metadata.create_all(bind=self.engine)
        StockService.reset_runtime_state()

        self.app = FastAPI()
        self.app.include_router(inventory.router, prefix="/inventory")
        self.app.include_router(settings_endpoint.router, prefix="/settings")
        self.app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(self.app)

        self._seed_users()
        self._seed_existing_item()

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        StockService.reset_runtime_state()
        settings.AUTH_SECRET_KEY = self._original_secret
        settings.STOCK_PRESENCE_CONFIRMATION_FRAMES = self._original_presence
        settings.STOCK_ABSENCE_CONFIRMATION_FRAMES = self._original_absence

    def _override_get_db(self):
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _seed_users(self):
        db = self.SessionLocal()
        try:
            db.add_all(
                [
                    User(
                        id=str(uuid.uuid4()),
                        username="admin",
                        email="admin@example.com",
                        hashed_password=auth_service.get_password_hash("admin-pass-123"),
                        is_active=True,
                        is_admin=True,
                    ),
                    User(
                        id=str(uuid.uuid4()),
                        username="operator",
                        email="operator@example.com",
                        hashed_password=auth_service.get_password_hash("operator-pass-123"),
                        is_active=True,
                        is_admin=False,
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

    def _seed_existing_item(self):
        db = self.SessionLocal()
        try:
            item = Item(
                id="ITEM001",
                name="可口可乐",
                category="饮料",
                aisle="A1",
                threshold=5,
                current_stock=2,
                status="low",
            )
            db.add(item)
            db.add_all(
                [
                    Item(
                        id="ITEM002",
                        name="Alpha stock",
                        category="Test",
                        aisle="A2",
                        threshold=5,
                        current_stock=9,
                        status="normal",
                    ),
                    Item(
                        id="ITEM003",
                        name="Beta stock",
                        category="Test",
                        aisle="A3",
                        threshold=5,
                        current_stock=0,
                        status="out",
                    ),
                ]
            )
            db.add(
                StockHistory(
                    item_id="ITEM001",
                    stock_level=2,
                )
            )
            db.add(
                Alert(
                    item_id="ITEM001",
                    alert_type="warning",
                    message="low stock",
                    status="active",
                )
            )
            db.add(
                LabelMapping(
                    detection_label="cola",
                    item_id="ITEM001",
                )
            )
            detection = Detection(
                item_id="ITEM001",
                detected_count=2,
                confidence=0.9,
                camera_id="camera_test",
            )
            db.add(detection)
            db.flush()
            db.add(
                DetectionBox(
                    detection_id=detection.id,
                    item_id="ITEM001",
                    camera_id="camera_test",
                    label="cola",
                    class_id=0,
                    x=12.0,
                    y=24.0,
                    w=64.0,
                    h=80.0,
                    confidence=0.9,
                    predicted_count=2,
                    count_model_version="test",
                )
            )
            db.commit()
        finally:
            db.close()

    def _auth_header(self, username: str) -> dict[str, str]:
        token = auth_service.create_access_token({"sub": username})
        return {"Authorization": f"Bearer {token}"}

    def test_settings_requires_authentication(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 401)

    def test_non_admin_cannot_update_settings(self):
        response = self.client.put(
            "/settings",
            json={"default_item_threshold": 8},
            headers=self._auth_header("operator"),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_get_and_update_settings(self):
        response = self.client.get("/settings", headers=self._auth_header("admin"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["default_item_threshold"], 10)
        self.assertEqual(response.json()["camera_default_sync_inventory"], False)

        update_response = self.client.put(
            "/settings",
            json={
                "default_item_threshold": 8,
                "stock_presence_confirmation_frames": 3,
                "stock_absence_confirmation_frames": 4,
                "camera_display_name": "答辩演示摄像头",
                "camera_location": "实验室货架A",
                "camera_default_sync_inventory": True,
            },
            headers=self._auth_header("admin"),
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["default_item_threshold"], 8)
        self.assertEqual(
            update_response.json()["stock_presence_confirmation_frames"],
            3,
        )
        self.assertEqual(
            update_response.json()["camera_display_name"],
            "答辩演示摄像头",
        )
        self.assertTrue(update_response.json()["camera_default_sync_inventory"])

    def test_updated_settings_control_stock_service_confirmation_frames(self):
        settings_response = self.client.put(
            "/settings",
            json={
                "stock_presence_confirmation_frames": 3,
                "stock_absence_confirmation_frames": 4,
            },
            headers=self._auth_header("admin"),
        )
        self.assertEqual(settings_response.status_code, 200)

        db = self.SessionLocal()
        try:
            item = db.query(Item).filter(Item.id == "ITEM001").first()
            item.current_stock = 6
            item.status = "normal"
            db.commit()
            db.refresh(item)

            first = StockService.process_detections(
                db=db,
                detections=[{"label": "cola", "confidence": 0.9}] * 2,
                camera_id="camera_settings_test",
            )
            db.refresh(item)
            self.assertEqual(item.status, "normal")
            self.assertEqual(first["pending_status_updates"][0]["frames_required"], 3)

            second = StockService.process_detections(
                db=db,
                detections=[{"label": "cola", "confidence": 0.9}] * 2,
                camera_id="camera_settings_test",
            )
            db.refresh(item)
            self.assertEqual(item.status, "normal")

            third = StockService.process_detections(
                db=db,
                detections=[{"label": "cola", "confidence": 0.9}] * 2,
                camera_id="camera_settings_test",
            )
            db.refresh(item)
            self.assertEqual(item.status, "low")
            self.assertEqual(third["status_changes"][0]["new_status"], "low")
        finally:
            db.close()

    def test_creating_item_writes_stock_history_and_initial_alert(self):
        response = self.client.post(
            "/inventory/",
            json={
                "id": "ITEM999",
                "name": "测试商品",
                "category": "饮料",
                "aisle": "Z1",
                "threshold": 5,
                "current_stock": 2,
            },
            headers=self._auth_header("admin"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "low")

        db = self.SessionLocal()
        try:
            history_count = (
                db.query(StockHistory)
                .filter(StockHistory.item_id == "ITEM999")
                .count()
            )
            alert_count = (
                db.query(Alert)
                .filter(Alert.item_id == "ITEM999", Alert.status == "active")
                .count()
            )
            self.assertEqual(history_count, 1)
            self.assertEqual(alert_count, 1)
        finally:
            db.close()

    def test_inventory_supports_current_stock_desc_sorting(self):
        response = self.client.get(
            "/inventory/",
            params={"order_by": "current_stock", "order_dir": "desc"},
            headers=self._auth_header("operator"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            ["ITEM002", "ITEM001", "ITEM003"],
        )

    def test_inventory_rejects_invalid_sort_parameters(self):
        bad_field_response = self.client.get(
            "/inventory/",
            params={"order_by": "not_a_column"},
            headers=self._auth_header("operator"),
        )
        bad_dir_response = self.client.get(
            "/inventory/",
            params={"order_dir": "sideways"},
            headers=self._auth_header("operator"),
        )

        self.assertEqual(bad_field_response.status_code, 422)
        self.assertEqual(bad_dir_response.status_code, 422)

    def test_inventory_reset_state_requires_admin(self):
        unauthenticated_response = self.client.post("/inventory/reset-state")
        operator_response = self.client.post(
            "/inventory/reset-state",
            headers=self._auth_header("operator"),
        )

        self.assertEqual(unauthenticated_response.status_code, 401)
        self.assertEqual(operator_response.status_code, 403)

    def test_admin_can_reset_inventory_state_without_deleting_catalog(self):
        response = self.client.post(
            "/inventory/reset-state",
            headers=self._auth_header("admin"),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items_reset"], 3)
        self.assertEqual(data["detections_deleted"], 1)
        self.assertEqual(data["detection_boxes_deleted"], 1)
        self.assertEqual(data["stock_history_deleted"], 1)
        self.assertEqual(data["alerts_deleted"], 1)

        db = self.SessionLocal()
        try:
            items = db.query(Item).order_by(Item.id).all()
            self.assertEqual([item.id for item in items], ["ITEM001", "ITEM002", "ITEM003"])
            self.assertTrue(all(item.current_stock == 0 for item in items))
            self.assertTrue(all(item.status == "out" for item in items))
            self.assertEqual(db.query(LabelMapping).count(), 1)
            self.assertEqual(db.query(Detection).count(), 0)
            self.assertEqual(db.query(DetectionBox).count(), 0)
            self.assertEqual(db.query(StockHistory).count(), 0)
            self.assertEqual(db.query(Alert).count(), 0)
        finally:
            db.close()

    def test_editing_inventory_stock_writes_history_and_resolves_or_creates_alerts(self):
        normalize_response = self.client.patch(
            "/inventory/ITEM001",
            json={"current_stock": 7},
            headers=self._auth_header("admin"),
        )
        self.assertEqual(normalize_response.status_code, 200)
        self.assertEqual(normalize_response.json()["status"], "normal")

        db = self.SessionLocal()
        try:
            history_count_after_normalize = (
                db.query(StockHistory)
                .filter(StockHistory.item_id == "ITEM001")
                .count()
            )
            active_alerts_after_normalize = (
                db.query(Alert)
                .filter(Alert.item_id == "ITEM001", Alert.status == "active")
                .count()
            )
            resolved_alerts_after_normalize = (
                db.query(Alert)
                .filter(Alert.item_id == "ITEM001", Alert.status == "resolved")
                .count()
            )
            self.assertEqual(history_count_after_normalize, 2)
            self.assertEqual(active_alerts_after_normalize, 0)
            self.assertEqual(resolved_alerts_after_normalize, 1)
        finally:
            db.close()

        out_response = self.client.patch(
            "/inventory/ITEM001",
            json={"current_stock": 0},
            headers=self._auth_header("admin"),
        )
        self.assertEqual(out_response.status_code, 200)
        self.assertEqual(out_response.json()["status"], "out")

        db = self.SessionLocal()
        try:
            history_count_after_out = (
                db.query(StockHistory)
                .filter(StockHistory.item_id == "ITEM001")
                .count()
            )
            active_alerts = (
                db.query(Alert)
                .filter(Alert.item_id == "ITEM001", Alert.status == "active")
                .all()
            )
            self.assertEqual(history_count_after_out, 3)
            self.assertEqual(len(active_alerts), 1)
            self.assertEqual(active_alerts[0].alert_type, "critical")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
