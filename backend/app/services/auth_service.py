"""
Authentication Service
Handles password hashing, JWT token generation, and user authentication
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User

# 密码加密配置
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    @staticmethod
    def get_secret_key() -> str:
        return settings.get_auth_secret_key()

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """生成密码哈希"""
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """创建 JWT token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode,
            AuthService.get_secret_key(),
            algorithm=settings.AUTH_ALGORITHM,
        )
        return encoded_jwt

    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
        """验证用户"""
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def get_current_user_from_token(token: str, db: Session) -> Optional[User]:
        """从 token 获取当前用户"""
        try:
            payload = jwt.decode(
                token,
                AuthService.get_secret_key(),
                algorithms=[settings.AUTH_ALGORITHM],
            )
            username: str = payload.get("sub")
            if username is None:
                return None
        except JWTError:
            return None

        user = db.query(User).filter(User.username == username).first()
        return user

auth_service = AuthService()
