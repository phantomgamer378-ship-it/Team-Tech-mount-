"""GET /api/health — liveness + service status (§19: health check from Phase 1)."""
from fastapi import APIRouter, Request

from app.config import settings
from app.models.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report app status + which services are loaded / in demo mode.

    Flutter should hit this first (from a phone: http://<LAN-IP>:8000/api/health)
    to confirm networking works before any app logic is debugged (§12).
    """
    services = getattr(request.app.state, "services", None)
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.VERSION,
        demo_mode=settings.DEMO_MODE,
        services=services.status() if services is not None else {},
    )
