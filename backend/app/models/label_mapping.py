from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.db.base_class import Base


class LabelMapping(Base):
    __tablename__ = "label_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    detection_label = Column(String, nullable=False, unique=True, index=True)
    item_id = Column(String, ForeignKey("items.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
