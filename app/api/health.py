from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "database_configured": bool(settings.database_url)}

