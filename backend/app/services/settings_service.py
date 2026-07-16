from app.core.config import settings
from app.models.system_settings import SystemSettings


class SettingsService:
    SETTINGS_ROW_ID = 1

    @classmethod
    def default_payload(cls) -> dict:
        return {
            "default_item_threshold": 10,
            "stock_presence_confirmation_frames": settings.STOCK_PRESENCE_CONFIRMATION_FRAMES,
            "stock_absence_confirmation_frames": settings.STOCK_ABSENCE_CONFIRMATION_FRAMES,
            "camera_display_name": "本地演示摄像头",
            "camera_location": "演示货架区域",
            "camera_default_sync_inventory": False,
        }

    @classmethod
    def get_or_create_settings(cls, db):
        settings_row = (
            db.query(SystemSettings)
            .filter(SystemSettings.id == cls.SETTINGS_ROW_ID)
            .first()
        )
        if settings_row:
            return settings_row

        settings_row = SystemSettings(
            id=cls.SETTINGS_ROW_ID,
            **cls.default_payload(),
        )
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
        return settings_row

    @classmethod
    def get_runtime_settings(cls, db):
        settings_row = (
            db.query(SystemSettings)
            .filter(SystemSettings.id == cls.SETTINGS_ROW_ID)
            .first()
        )
        if settings_row:
            return settings_row

        return SystemSettings(
            id=cls.SETTINGS_ROW_ID,
            **cls.default_payload(),
        )

    @classmethod
    def update_settings(cls, db, update_data: dict):
        settings_row = cls.get_or_create_settings(db)
        for field, value in update_data.items():
            setattr(settings_row, field, value)
        db.commit()
        db.refresh(settings_row)
        return settings_row


settings_service = SettingsService()
