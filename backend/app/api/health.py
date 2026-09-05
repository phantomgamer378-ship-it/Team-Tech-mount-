"""GET /api/health — liveness + per-service status + storage + privacy mode.

§OBSERVABILITY: health check exists from Phase 1; §19: structured logging.
Flutter should hit this first (phone: http://<LAN-IP>:8000/api/health) to
confirm networking works before any app logic is debugged (§12).
"""
from fastapi import APIRouter, Request

from app.config import settings
from app.database import database as db
from app.models.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    services = getattr(request.app.state, "services", None)
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.VERSION,
        demo_mode=settings.DEMO_MODE,
        privacy_mode=settings.PRIVACY_MODE,
        database=db.check_health(),
        services=services.status() if services is not None else {},
    )
