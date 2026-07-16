from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models
from app.api.v1.api import api_router
from app.core.config import settings
from app.db.base_class import Base
from app.db.database import engine

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

default_cors_origins = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]

configured_cors_origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
cors_origins = list(dict.fromkeys(default_cors_origins + configured_cors_origins))

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"message": "Welcome to YOLOv8 Supermarket Monitor API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
