from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import audit, facts, prefs
from app.config import get_settings
from app.db import get_session
from app.llm import Gateway, LLMError, Tier
from app.models import Employment, LlmUsage, ProfileFact

router = APIRouter(prefix="/api")


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        session.execute(text("select 1"))
        db = "ok"
    except Exception as e:  # report, don't crash the health check
        db = f"error: {e.__class__.__name__}"
    return {"status": "ok" if db == "ok" else "degraded", "db": db, "llm_engine": get_settings().llm_engine}


# ---------- settings ----------

@router.get("/settings")
def read_settings(session: Session = Depends(get_session)) -> dict[str, Any]:
    return prefs.get_all(session)


@router.put("/settings/{section}")
def write_settings(section: str, body: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    if section not in prefs.SECTIONS:
        raise HTTPException(404, f"unknown settings section {section!r}")
    try:
        saved = prefs.put_section(session, section, body)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from e
    audit.record(session, "user", "settings.update", section, value=saved.model_dump())
    return saved.model_dump()


# ---------- facts ----------

@router.post("/facts/sync")
def sync_facts(session: Session = Depends(get_session)) -> dict[str, int]:
    try:
        return facts.sync_from_file(session, get_settings().facts_file)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from e


@router.get("/facts")
def list_facts(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.scalars(select(ProfileFact).order_by(ProfileFact.id)).all()
    employers = {e.id: e.company for e in session.scalars(select(Employment))}
    return {
        "facts": [
            {
                "id": f.id, "kind": f.kind, "employer": employers.get(f.employer_id), "text": f.text,
                "skills": f.skills, "metric": f.metric, "needs_confirmation": f.needs_confirmation, "note": f.note,
            }
            for f in rows
        ],
        "usable": len(facts.usable_facts(session)),
    }


# ---------- llm ----------

@router.get("/llm/usage")
def llm_usage(session: Session = Depends(get_session)) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = session.execute(
        select(LlmUsage.task, func.count(), func.sum(LlmUsage.input_tokens),
               func.sum(LlmUsage.output_tokens), func.sum(LlmUsage.cost_usd_equiv),
               func.count().filter(LlmUsage.ok.is_(False)))
        .where(LlmUsage.at >= since).group_by(LlmUsage.task).order_by(LlmUsage.task)
    ).all()
    gateway = Gateway(session)
    return {
        "calls_today": gateway.calls_today(),
        "daily_limit": prefs.get_section(session, "llm").daily_call_limit,
        "last_30_days": [
            {"task": t, "calls": c, "input_tokens": i or 0, "output_tokens": o or 0,
             "cost_usd_equiv": float(cost or 0), "errors": err}
            for t, c, i, o, cost, err in rows
        ],
    }


class PingOut(BaseModel):
    ok: bool
    model: str | None = None
    reply: Any = None
    error: str | None = None


@router.post("/llm/ping")
def llm_ping(session: Session = Depends(get_session)) -> PingOut:
    """One tiny structured call to prove the engine (and your Claude login) works."""
    schema = {
        "type": "object",
        "properties": {"role_family": {"type": "string", "enum": ["ai_engineer", "java_backend", "other"]}},
        "required": ["role_family"],
        "additionalProperties": False,
    }
    try:
        result = Gateway(session).complete(
            task="llm.ping", tier=Tier.SMALL, schema=schema,
            system="You classify job titles into a role family.",
            prompt='Job title: "LLM Application Developer"',
        )
    except LLMError as e:
        return PingOut(ok=False, error=str(e))
    return PingOut(ok=True, model=result.model, reply=result.data)
