from fastapi import APIRouter, Request, UploadFile, File, HTTPException
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["analyze"])

@router.post("/audio")
async def analyze_audio(request: Request, audio: UploadFile = File(...)):
    """Analyze an uploaded audio file for voice deepfakes and scams."""
    services = request.app.state.services
    
    # Read the uploaded file
    try:
        content = await audio.read()
    except Exception as e:
        log.error(f"Failed to read audio file: {e}")
        raise HTTPException(status_code=400, detail="Failed to read audio file")
        
    # Phase 8: Mock wiring to the processor and risk engine
    # In a full implementation, this calls audio_processor, voice_detector, asr, scam_detector, risk_engine
    
    # Process audio
    try:
        audio_array, duration = services.audio.process_upload(content)
    except Exception as e:
        log.error(f"Audio processing failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    # AI Voice Detection
    voice_res = services.voice.analyze(audio_array)
    voice_risk = voice_res.get("risk_score", 0.0)
    
    # ASR & Scam
    asr_res = services.asr.transcribe(audio_array)
    scam_res = services.scam.analyze(asr_res.get("transcript", ""))
    scam_risk = scam_res.get("scam_score", 0.0)
    
    # Fusion
    fusion_res = services.risk.fuse(voice_risk=voice_risk, scam_risk=scam_risk)
    
    return {
        "voice": voice_res,
        "asr": asr_res,
        "scam": scam_res,
        "fusion": fusion_res
    }
