"""
Initialize database with admin user
Creates admin account: username=admin, password=88888888
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
sys.path.insert(0, str(backend_path))

from app.db.database import SessionLocal
from app.models.user import User
from app.services.auth_service import auth_service
import uuid

def create_admin_user():
    """创建管理员账号"""
    db = SessionLocal()

    try:
        # 检查管理员是否已存在
        existing_admin = db.query(User).filter(User.username == "admin").first()
        if existing_admin:
            print("[INFO] Admin user already exists")
            return

        # 创建管理员账号
        admin = User(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@example.com",
            hashed_password=auth_service.get_password_hash("88888888"),
            is_active=True,
            is_admin=True
        )

        db.add(admin)
        db.commit()

        print("[OK] Admin user created successfully")
        print("    Username: admin")
        print("    Password: 88888888")

    except Exception as e:
        print(f"[ERROR] Failed to create admin user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 50)
    print("Creating Admin User")
    print("=" * 50)
    create_admin_user()
    print("=" * 50)
