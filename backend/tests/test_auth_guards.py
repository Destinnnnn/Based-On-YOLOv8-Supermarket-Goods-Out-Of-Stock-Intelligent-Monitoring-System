import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi import WebSocketException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.v1.endpoints.auth import authenticate_websocket, extract_websocket_token
from app.api.v1.endpoints import alerts, inventory, label_mappings, reports
from app.core.config import settings
from app.db.base_class import Base
from app.db.database import get_db
from app.models.alert import Alert
from app.models.item import Item
from app.models.user import User
from app.services.auth_service import auth_service


class AuthGuardTests(unittest.TestCase):
    def setUp(self):
        self._original_secret = getattr(settings, "AUTH_SECRET_KEY", None)
        self._original_expire = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", None)
        settings.AUTH_SECRET_KEY = "test-auth-secret-0123456789"
        settings.ACCESS_TOKEN_EXPIRE_MINUTES = 60

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

        self.app = FastAPI()
        self.app.include_router(inventory.router, prefix="/inventory")
        self.app.include_router(label_mappings.router, prefix="/label-mappings")
        self.app.include_router(alerts.router, prefix="/alerts")
        self.app.include_router(reports.router, prefix="/reports")
        self.app.dependency_overrides[get_db] = self._override_get_db

        self.client = TestClient(self.app)
        self._seed_data()

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        settings.AUTH_SECRET_KEY = self._original_secret
        settings.ACCESS_TOKEN_EXPIRE_MINUTES = self._original_expire

    def _override_get_db(self):
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _seed_data(self):
        db = self.SessionLocal()
        try:
            admin = User(
                id=str(uuid.uuid4()),
                username="admin",
                email="admin@example.com",
                hashed_password=auth_service.get_password_hash("admin-pass-123"),
                is_active=True,
                is_admin=True,
            )
            user = User(
                id=str(uuid.uuid4()),
                username="operator",
                email="operator@example.com",
                hashed_password=auth_service.get_password_hash("operator-pass-123"),
                is_active=True,
                is_admin=False,
            )
            item = Item(
                id="ITEM001",
                name="可口可乐",
                category="饮料",
                aisle="A1",
                threshold=5,
                current_stock=4,
                status="low",
            )
            alert = Alert(
                item_id="ITEM001",
                alert_type="warning",
                message="low stock",
                status="active",
            )
            db.add_all([admin, user, item, alert])
            db.commit()
        finally:
            db.close()

    def _auth_header(self, username: str) -> dict[str, str]:
        token = auth_service.create_access_token({"sub": username})
        return {"Authorization": f"Bearer {token}"}

    def test_inventory_requires_authentication(self):
        response = self.client.get("/inventory/")
        self.assertEqual(response.status_code, 401)

    def test_reports_require_authentication(self):
        response = self.client.get("/reports/summary")
        self.assertEqual(response.status_code, 401)

    def test_regular_user_cannot_mutate_inventory(self):
        response = self.client.post(
            "/inventory/",
            json={
                "id": "ITEM999",
                "name": "测试商品",
                "category": "饮料",
                "aisle": "Z1",
                "threshold": 3,
            },
            headers=self._auth_header("operator"),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_mutate_inventory(self):
        response = self.client.post(
            "/inventory/",
            json={
                "id": "ITEM999",
                "name": "测试商品",
                "category": "饮料",
                "aisle": "Z1",
                "threshold": 3,
            },
            headers=self._auth_header("admin"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "ITEM999")

    def test_extract_websocket_token_from_query_string(self):
        websocket = SimpleNamespace(
            query_params={"token": "query-token"},
            headers={},
        )
        self.assertEqual(extract_websocket_token(websocket), "query-token")

    def test_authenticate_websocket_rejects_missing_token(self):
        db = self.SessionLocal()
        websocket = SimpleNamespace(query_params={}, headers={})
        try:
            with self.assertRaises(WebSocketException) as context:
                authenticate_websocket(websocket, db)
            self.assertEqual(context.exception.code, status.WS_1008_POLICY_VIOLATION)
        finally:
            db.close()

    def test_authenticate_websocket_accepts_query_token(self):
        token = auth_service.create_access_token({"sub": "operator"})
        db = self.SessionLocal()
        websocket = SimpleNamespace(
            query_params={"token": token},
            headers={},
        )
        try:
            user = authenticate_websocket(websocket, db)
            self.assertEqual(user.username, "operator")
        finally:
            db.close()


class AuthSecretConfigTests(unittest.TestCase):
    def test_access_token_requires_configured_secret_key(self):
        original_secret = getattr(settings, "AUTH_SECRET_KEY", None)
        try:
            settings.AUTH_SECRET_KEY = None
            with self.assertRaises(RuntimeError):
                auth_service.create_access_token({"sub": "operator"})
        finally:
            settings.AUTH_SECRET_KEY = original_secret


if __name__ == "__main__":
    unittest.main()
