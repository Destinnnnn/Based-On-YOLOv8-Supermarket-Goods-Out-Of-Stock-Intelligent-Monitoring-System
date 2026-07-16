from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from app.db.base_class import Base

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String, ForeignKey("items.id"), nullable=False, index=True)
    alert_type = Column(String, nullable=False)  # 'warning', 'critical'
    message = Column(String, nullable=False)
    status = Column(String, default="active")  # 'active', 'resolved'
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime)
