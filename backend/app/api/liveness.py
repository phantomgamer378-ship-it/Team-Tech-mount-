from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/liveness", tags=["liveness"])

class StartRequest(BaseModel):
    session_id: str

class VerifyRequest(BaseModel):
    session_id: str
    spoken_text: str

@router.post("/start")
def start_challenge(req: StartRequest, request: Request):
    """Start a liveness challenge."""
    services = request.app.state.services
    if not hasattr(services, 'liveness'):
        raise HTTPException(status_code=500, detail="Liveness service not available")
    return services.liveness.start_challenge(req.session_id)

@router.post("/verify")
def verify_challenge(req: VerifyRequest, request: Request):
    """Verify a liveness challenge."""
    services = request.app.state.services
    if not hasattr(services, 'liveness'):
        raise HTTPException(status_code=500, detail="Liveness service not available")
    return services.liveness.verify(req.session_id, req.spoken_text)
