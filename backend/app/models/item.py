from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime
from app.db.base_class import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)
    aisle = Column(String)
    current_stock = Column(Integer, default=0)
    threshold = Column(Integer, default=10)
    status = Column(String, default="normal")  # 'normal', 'low', 'out'
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
