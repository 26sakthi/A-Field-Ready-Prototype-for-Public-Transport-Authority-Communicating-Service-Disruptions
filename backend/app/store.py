"""In-memory repository for the prototype.

Deterministic and laptop-friendly (no DB setup). The interface mirrors what a
SQLite/Postgres+PostGIS layer would expose, so it can be swapped later
(Architecture 10). Also records the audit trail.
"""
from __future__ import annotations

import threading

from engine.domain import (
    AuditEntry,
    Incident,
    OfficialEvent,
    Report,
    Reporter,
    VerificationEvent,
    utcnow,
)


class Store:
    def __init__(self) -> None:
        self.reports: dict[str, Report] = {}
        self.incidents: dict[str, Incident] = {}
        self.reporters: dict[str, Reporter] = {}
        self.verifications: dict[str, VerificationEvent] = {}
        self.official_events: dict[str, OfficialEvent] = {}
        self.audit: list[AuditEntry] = []
        self._seen_sync_uuids: set[str] = set()
        self.lock = threading.RLock()

    def reports_for(self, incident_id: str) -> list[Report]:
        return [r for r in self.reports.values() if r.incident_id == incident_id]

    def verifications_for(self, incident_id: str) -> list[VerificationEvent]:
        return [v for v in self.verifications.values() if v.incident_id == incident_id]

    def log(self, entity_type: str, entity_id: str, actor_id: str, actor_role: str, change: str) -> None:
        import uuid

        self.audit.append(
            AuditEntry(
                id=f"aud_{uuid.uuid4().hex[:10]}",
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                actor_role=actor_role,
                change=change,
                created_at=utcnow(),
            )
        )

    def seen_sync(self, client_uuid: str) -> bool:
        return client_uuid in self._seen_sync_uuids

    def mark_sync(self, client_uuid: str) -> None:
        self._seen_sync_uuids.add(client_uuid)

    def reset(self) -> None:
        self.__init__()


STORE = Store()
