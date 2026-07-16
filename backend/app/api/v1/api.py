from fastapi import APIRouter

from app.api.v1.endpoints import alerts, auth, camera, inventory, label_mappings, reports, settings

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(camera.router, prefix="/camera", tags=["camera"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(label_mappings.router, prefix="/label-mappings", tags=["label-mappings"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
