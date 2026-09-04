"""
Persistence layer — SQLite for the prototype (§17), wired in a later phase.

Planned tables: users (minimal), sessions, analysis_results, threat_events.
PROTOTYPE: SQLite file. FUTURE PRODUCT: Postgres behind the same interface.

PRODUCTION WOULD DO BETTER (§23): encryption at rest, consent/retention
policies for any stored audio, no raw-audio persistence at all.
"""
from app.config import settings

DATABASE_PATH = settings.DATABASE_PATH


def get_connection():
    raise NotImplementedError(
        "Database wiring arrives in a later phase — see §17 (users, sessions, "
        "analysis_results, threat_events tables)."
    )
