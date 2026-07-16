from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.db.base_class import Base


class DetectionBox(Base):
    __tablename__ = "detection_boxes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    detection_id = Column(Integer, ForeignKey("detections.id"), nullable=False, index=True)
    item_id = Column(String, ForeignKey("items.id"), nullable=False, index=True)
    camera_id = Column(String, index=True)
    label = Column(String, nullable=False, index=True)
    class_id = Column(Integer)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    w = Column(Float, nullable=False)
    h = Column(Float, nullable=False)
    confidence = Column(Float)
    predicted_count = Column(Integer, nullable=False, default=1)
    count_model_version = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
