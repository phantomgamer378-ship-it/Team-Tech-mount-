"""
Configuration management (§19) — everything comes from backend/.env.

Never hardcode secrets, paths or model names in code (§23). Copy
.env.example to .env and adjust values there.

PROTOTYPE NOTE: permissive CORS + demo defaults are intentional for the
hackathon round. Production would use a secrets manager, locked-down CORS
and real database credentials.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ — the folder that contains this app package and .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() == "true"


class Settings:
    """Plain, readable settings object — deliberately not clever."""

    APP_NAME: str = "Voice Clone Shield"
    VERSION: str = "0.1.0"

    # DEMO MODE (§20): when True and a real model isn't loaded, services return
    # clearly-labelled mock output instead of crashing. This is a
    # launch-blocking requirement, not a nice-to-have (§24).
    DEMO_MODE: bool = _bool("DEMO_MODE", True)

    # Model settings
    MODEL_PATH: str = os.getenv("MODEL_PATH", "")  # override all model storage locations
    ASR_MODEL: str = os.getenv("ASR_MODEL", "ai4bharat/indic-conformer-600m-multilingual")
    DEVICE: str = os.getenv("DEVICE", "cpu")  # "cpu" | "cuda" | "mps"

    # Voice detector (Phase 3) — AASIST-L checkpoint.
    # Primary URL is the HF repo the master prompt points at; fallback is the
    # official clovaai GitHub copy of the same file.
    VOICE_MODEL_PATH: str = os.getenv(
        "VOICE_MODEL_PATH", str(BASE_DIR / "models" / "AASIST-L.pth")
    )
    VOICE_MODEL_URL: str = os.getenv(
        "VOICE_MODEL_URL",
        "https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST-L/resolve/main/AASIST-L.pth",
    )
    VOICE_MODEL_URL_FALLBACK: str = os.getenv(
        "VOICE_MODEL_URL_FALLBACK",
        "https://raw.githubusercontent.com/clovaai/aasist/main/models/weights/AASIST-L.pth",
    )

    # Server (§12): 0.0.0.0 so a phone/emulator on the same Wi-Fi can reach us.
    # Android emulator specifically reaches the host via 10.0.2.2.
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Storage (SQLite lands in a later phase — §17)
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/shield.db")

    # Uploads — enforced properly when audio upload lands in Phase 8.
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "10"))


settings = Settings()
