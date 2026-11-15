from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(session: Session, actor: str, action: str, entity_ref: str | None = None, **details: Any) -> None:
    session.add(AuditLog(actor=actor, action=action, entity_ref=entity_ref, details=details))
