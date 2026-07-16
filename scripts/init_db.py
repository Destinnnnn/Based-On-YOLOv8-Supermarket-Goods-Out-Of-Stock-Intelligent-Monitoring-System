"""
Database initialization script
Creates all tables and adds seed data for testing
"""
import sys
from pathlib import Path

# Add backend to path
project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
sys.path.insert(0, str(backend_path))

from app.db.database import engine
from app.db.base_class import Base
from app.models.item import Item
from app.models.detection import Detection
from app.models.detection_box import DetectionBox
from app.models.alert import Alert
from app.models.label_mapping import LabelMapping
from app.models.stock_history import StockHistory
from app.models.user import User
from sqlalchemy.orm import Session
from app.services.demo_seed_service import build_full_demo_seed_catalog

def init_db():
    """Create all tables"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[OK] Tables created successfully")

def add_seed_data():
    """Reset and add the full training-label inventory and mapping catalog."""
    print("\nAdding seed data...")

    seed_items, seed_label_mappings = build_full_demo_seed_catalog()

    from app.db.database import SessionLocal
    db = SessionLocal()

    try:
        db.query(DetectionBox).delete()
        db.query(LabelMapping).delete()
        db.query(Detection).delete()
        db.query(StockHistory).delete()
        db.query(Alert).delete()
        db.query(Item).delete()
        db.flush()

        for item_data in seed_items:
            db.add(Item(**item_data))

        db.flush()

        for mapping_data in seed_label_mappings:
            db.add(LabelMapping(**mapping_data))

        db.commit()
        print(f"[OK] Added {len(seed_items)} training-label products")
        print(f"[OK] Added {len(seed_label_mappings)} label mappings")
    except Exception as e:
        print(f"[ERROR] Error adding seed data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Create data directory
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)

    print("=" * 50)
    print("YOLOv8 Stock Monitor - Database Initialization")
    print("=" * 50)

    init_db()
    add_seed_data()

    print("\n" + "=" * 50)
    print("Database initialization completed!")
    print("=" * 50)
