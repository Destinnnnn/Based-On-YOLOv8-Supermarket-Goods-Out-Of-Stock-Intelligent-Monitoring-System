from typing import List, Optional, Union
from pathlib import Path
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "YOLOv8 Supermarket Monitor API"
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.parent
    YOLO_CONF_THRESHOLD: float = 0.15
    YOLO_IOU_THRESHOLD: float = 0.60
    AUTH_SECRET_KEY: Optional[str] = None
    AUTH_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    STOCK_PRESENCE_CONFIRMATION_FRAMES: int = 2
    STOCK_ABSENCE_CONFIRMATION_FRAMES: int = 3
    
    # BACKEND_CORS_ORIGINS is a JSON-formatted list of origins
    # e.g: '["http://localhost", "http://localhost:3000"]'
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @validator("YOLO_CONF_THRESHOLD", "YOLO_IOU_THRESHOLD")
    def validate_probability_threshold(cls, v: float) -> float:
        if 0.0 <= v <= 1.0:
            return v
        raise ValueError("YOLO thresholds must be between 0.0 and 1.0")

    @validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    def validate_access_token_expiry(cls, v: int) -> int:
        if v >= 1:
            return v
        raise ValueError("Access token expiry must be greater than 0")

    @validator(
        "STOCK_PRESENCE_CONFIRMATION_FRAMES",
        "STOCK_ABSENCE_CONFIRMATION_FRAMES",
    )
    def validate_confirmation_frames(cls, v: int) -> int:
        if v >= 1:
            return v
        raise ValueError("Stock confirmation frames must be greater than 0")

    def get_auth_secret_key(self) -> str:
        if self.AUTH_SECRET_KEY:
            return self.AUTH_SECRET_KEY
        raise RuntimeError(
            "AUTH_SECRET_KEY is not configured. Set it in the environment or .env."
        )

    class Config:
        case_sensitive = True
        env_file = str(Path(__file__).resolve().parents[3] / ".env")

settings = Settings()
