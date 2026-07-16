from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_active_admin
from app.db.database import get_db
from app.models.user import User
from app.schemas.system_settings import (
    SystemSettingsResponse,
    SystemSettingsUpdate,
)
from app.services.settings_service import settings_service

router = APIRouter()


@router.get("/", response_model=SystemSettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    return settings_service.get_or_create_settings(db)


@router.put("/", response_model=SystemSettingsResponse)
def update_settings(
    settings_in: SystemSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    update_data = settings_in.model_dump(exclude_unset=True)
    return settings_service.update_settings(db, update_data)
