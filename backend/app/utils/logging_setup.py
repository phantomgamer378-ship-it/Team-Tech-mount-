"""
Structured logging setup (§19 — health check + structured logging from Phase 1).

PROTOTYPE: readable plain-text logs are fine here. Production would ship JSON
logs to a central system with request IDs and PII scrubbing (§23 — and never
log raw audio or secrets).
"""
import logging
import sys

from app.config import settings


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)
    root.handlers = [handler]
