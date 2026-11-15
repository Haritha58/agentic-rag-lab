"""Interview prep and Coach endpoints (Phase 5a)."""

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import audit, coach, prep
from app.db import get_session
from app.llm import Engine, Gateway, LLMError
from app.llm.gateway import default_engine
from app.models import Application, CoachMessage, CoachSession, Company, Job, JobScore, TopicSelfRating

router = APIRouter(prefix="/api")


def get_llm_engine() -> Engine:
    """Overridden in tests with FakeEngine."""
    return default_engine()


def _llm_failed(e: LLMError) -> JSONResponse:
    # A returned (not raised) response keeps the transaction, so the failed call stays in the usage ledger.
    return JSONResponse({"detail": str(e)}, status_code=502)


# ---------- prep ----------

def _prof_out(t: str, p: prep.Proficiency) -> dict[str, Any]:
    return {"topic": t, "label": prep.TOPIC_LABELS[t], "score": p.score, "evidence": p.evidence,
            "self_rating": p.self_rating, "last_at": p.last_at}


@router.get("/prep/topics")
def list_topics(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [_prof_out(t, p) for t, p in prep.proficiencies(session).items()]


class SelfRatingIn(BaseModel):
    rating: int | None = Field(None, ge=0, le=5, description="null clears it")


@router.put("/prep/topics/{topic}")
def set_self_rating(topic: str, body: SelfRatingIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    if topic not in prep.TOPICS:
        raise HTTPException(404, "unknown topic")
    row = session.get(TopicSelfRating, topic)
    if body.rating is None:
        if row:
            session.delete(row)
    elif row:
        row.rating = body.rating
    else:
        session.add(TopicSelfRating(topic=topic, rating=body.rating))
    session.flush()
    prep.refresh_readiness(session)
    return _prof_out(topic, prep.proficiencies(session)[topic])


@router.get("/prep/jobs")
def prep_jobs(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Shortlisted or applied-to jobs with their readiness."""
    rows = session.execute(
        select(Job, Company, JobScore).join(Company, Job.company_id == Company.id)
        .outerjoin(JobScore, JobScore.job_id == Job.id)
        # Jobs you've applied to stay here even if you never shortlisted them.
        .where(or_(Job.user_status == "shortlisted", Job.id.in_(select(Application.job_id))))
        .order_by(JobScore.opportunity.desc().nulls_last())
    ).all()
    out = []
    for job, company, score in rows:
        readiness, breakdown = prep.job_readiness(session, job)
        out.append({"id": job.id, "title": job.title, "company": company.name, "status": job.status,
                    "suitability": score.suitability if score else None,
                    "opportunity": score.opportunity if score else None,
                    "readiness": readiness, "readiness_breakdown": breakdown})
    return out


@router.get("/prep/jobs/{job_id}")
def prep_job(job_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    readiness, breakdown = prep.job_readiness(session, job)
    return {"id": job.id, "title": job.title, "company": session.get(Company, job.company_id).name,
            "readiness": readiness, "readiness_breakdown": breakdown}


# ---------- coach ----------

class SessionIn(BaseModel):
    mode: Literal["learn", "quiz", "mock", "readiness", "story", "project"]
    job_id: int | None = None
    round_type: str | None = None
    topic: str | None = None
    interview_date: date | None = None
    project_doc: str | None = None

    @model_validator(mode="after")
    def check(self) -> "SessionIn":
        if self.round_type is not None and self.round_type not in coach.ROUND_TYPES:
            raise ValueError(f"round_type must be one of {sorted(coach.ROUND_TYPES)}")
        if self.mode == "mock" and self.round_type is None:
            raise ValueError("a mock interview needs a round_type")
        if self.topic is not None and self.topic not in prep.TOPICS:
            raise ValueError("unknown topic")
        if self.mode == "project" and self.project_doc not in coach.list_guides():
            raise ValueError("a project deep-dive needs one of the study guides in data/interview_prep")
        return self


def _msg_out(m: CoachMessage) -> dict[str, Any]:
    return {"id": m.id, "role": m.role, "content": m.content, "assessment": m.assessment, "at": m.at}


def _session_out(session: Session, cs: CoachSession, with_messages: bool = False) -> dict[str, Any]:
    job = session.get(Job, cs.job_id) if cs.job_id else None
    out = {
        "id": cs.id, "mode": cs.mode, "round_type": cs.round_type, "round_label": coach.ROUND_TYPES.get(cs.round_type or ""),
        "topic": cs.topic, "topic_label": prep.TOPIC_LABELS.get(cs.topic or ""), "interview_date": cs.interview_date,
        "project_doc": cs.project_doc, "project_label": coach.list_guides().get(cs.project_doc or "") if cs.project_doc else None,
        "status": cs.status, "started_at": cs.started_at, "ended_at": cs.ended_at, "summary": cs.summary,
        "readiness_before": cs.readiness_before, "readiness_after": cs.readiness_after,
        "job": {"id": job.id, "title": job.title, "company": session.get(Company, job.company_id).name} if job else None,
    }
    if with_messages:
        msgs = coach.messages_of(session, cs)
        out["messages"] = [_msg_out(m) for m in msgs]
        out["topic_scores"] = coach.topic_scores(msgs)
    return out


def _get(session: Session, session_id: int) -> CoachSession:
    cs = session.get(CoachSession, session_id)
    if cs is None:
        raise HTTPException(404, "coach session not found")
    return cs


@router.get("/coach/meta")
def coach_meta() -> dict[str, Any]:
    return {"round_types": coach.ROUND_TYPES, "topics": prep.TOPIC_LABELS, "projects": coach.list_guides()}


@router.get("/coach/sessions")
def list_sessions(job_id: int | None = None, limit: int = 50, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    stmt = select(CoachSession).order_by(CoachSession.id.desc()).limit(limit)
    if job_id is not None:
        stmt = stmt.where(CoachSession.job_id == job_id)
    counts = dict(session.execute(
        select(CoachMessage.session_id, func.count()).where(CoachMessage.role == "user").group_by(CoachMessage.session_id)
    ).all())
    return [{**_session_out(session, cs), "answers": counts.get(cs.id, 0)} for cs in session.scalars(stmt)]


@router.post("/coach/sessions", status_code=201)
def create_session(body: SessionIn, session: Session = Depends(get_session),
                   engine: Engine = Depends(get_llm_engine)) -> Any:
    if body.job_id is not None and session.get(Job, body.job_id) is None:
        raise HTTPException(404, "job not found")
    try:
        cs = coach.start(session, Gateway(session, engine), **body.model_dump())
    except LLMError as e:
        return _llm_failed(e)
    audit.record(session, "user", "coach.session_started", f"coach_session:{cs.id}", mode=cs.mode, job_id=cs.job_id)
    return _session_out(session, cs, with_messages=True)


@router.get("/coach/sessions/{session_id}")
def get_coach_session(session_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _session_out(session, _get(session, session_id), with_messages=True)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


@router.post("/coach/sessions/{session_id}/messages")
def send_message(session_id: int, body: MessageIn, session: Session = Depends(get_session),
                 engine: Engine = Depends(get_llm_engine)) -> Any:
    cs = _get(session, session_id)
    if cs.status != "active":
        raise HTTPException(409, "this session has ended; start a new one")
    try:
        user_msg, coach_msg, done = coach.reply(session, Gateway(session, engine), cs, body.content.strip())
    except LLMError as e:
        return _llm_failed(e)
    return {"user": _msg_out(user_msg), "coach": _msg_out(coach_msg), "done": done}


@router.post("/coach/sessions/{session_id}/end")
def end_session(session_id: int, session: Session = Depends(get_session),
                engine: Engine = Depends(get_llm_engine)) -> Any:
    cs = _get(session, session_id)
    if cs.status != "active":
        raise HTTPException(409, "already ended")
    try:
        coach.end(session, Gateway(session, engine), cs)
    except LLMError as e:
        return _llm_failed(e)
    audit.record(session, "user", "coach.session_ended", f"coach_session:{cs.id}",
                 readiness_before=cs.readiness_before, readiness_after=cs.readiness_after)
    return _session_out(session, cs, with_messages=True)
