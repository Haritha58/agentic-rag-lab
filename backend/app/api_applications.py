"""Application tracker: applications, any number of interview rounds, and evidence-backed status history.

Everything here records what you did. Nothing here applies, submits or emails anyone.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, coach, prefs
from app.config import get_settings
from app.db import get_session
from app.models import (
    APPLICATION_STATUSES, EMAIL_CATEGORIES, ROUND_STATUSES, Application, Company, Email, InterviewRound, Job, StatusEvent,
)

router = APIRouter(prefix="/api")

IST = ZoneInfo("Asia/Kolkata")
FOLLOW_UP_DAYS = 7
# Statuses where you're still waiting on the company, so a follow-up reminder makes sense.
WAITING = ("applied", "viewed", "screening", "no_response")
# Adding a round to an application in one of these moves it to "interviewing".
BEFORE_INTERVIEWS = ("applied", "viewed", "screening", "no_response")

STATUS_LABELS = {
    "applied": "Applied", "viewed": "Application viewed", "screening": "Recruiter screening",
    "interviewing": "Interviewing", "offer": "Offer received", "accepted": "Offer accepted",
    "rejected": "Rejected", "withdrawn": "Withdrawn", "no_response": "No response",
}
CHANNELS = {
    "company_site": "Company careers site", "linkedin": "LinkedIn", "naukri": "Naukri", "indeed": "Indeed",
    "instahyre": "Instahyre", "wellfound": "Wellfound", "referral": "Referral", "recruiter": "Recruiter reached out",
    "other": "Other",
}
# Each round type maps to the Coach mock round that prepares you for it.
ROUND_TYPES = {
    "hr_screen": ("Recruiter / HR screen", "behavioral"),
    "coding": ("Coding (DSA)", "coding"),
    "technical_java": ("Technical: Java & Spring", "technical_java"),
    "technical_python": ("Technical: Python", "technical_python"),
    "technical_ai": ("Technical: AI / LLM", "technical_ai"),
    "system_design": ("System design", "system_design"),
    "assignment": ("Take-home assignment", "coding"),
    "managerial": ("Hiring manager", "managerial"),
    "behavioral": ("Behavioral / culture fit", "behavioral"),
    "client": ("Client round", "technical_ai"),
    "final": ("Final / leadership", "managerial"),
    "other": ("Other", "behavioral"),
}
assert all(c in coach.ROUND_TYPES for _, c in ROUND_TYPES.values())
ROUND_STATUS_LABELS = {
    "scheduled": "Scheduled", "completed": "Done, waiting for result", "cleared": "Cleared",
    "not_cleared": "Not cleared", "cancelled": "Cancelled",
}
ROUND_MODES = ("video", "phone", "onsite")


def _resume_versions(main: str) -> list[str]:
    """Your main resume first, then the drafts kept in data/resumes."""
    folder = get_settings().data_dir / "resumes"
    drafts = sorted((p.name for p in folder.glob("*.pdf")), reverse=True) if folder.exists() else []
    return ([main] if main else []) + [d for d in drafts if d != main]


def _as_ist(dt: datetime | None) -> datetime | None:
    # A browser datetime-local value has no zone; you're in India, so read it as IST.
    return dt.replace(tzinfo=IST) if dt is not None and dt.tzinfo is None else dt


def _round_out(r: InterviewRound) -> dict[str, Any]:
    label, coach_round = ROUND_TYPES.get(r.round_type, (r.round_type, "behavioral"))
    return {
        "id": r.id, "round_no": r.round_no, "round_type": r.round_type, "round_type_label": label,
        "coach_round": coach_round, "label": r.label, "scheduled_at": r.scheduled_at, "mode": r.mode,
        "interviewer": r.interviewer, "status": r.status, "questions": r.questions, "feedback": r.feedback,
        "self_rating": r.self_rating,
    }


def _rounds(session: Session, app_id: int) -> list[InterviewRound]:
    return list(session.scalars(
        select(InterviewRound).where(InterviewRound.application_id == app_id).order_by(InterviewRound.round_no)
    ))


def _app_out(session: Session, a: Application, detail: bool = False) -> dict[str, Any]:
    rounds = _rounds(session, a.id)
    now = datetime.now(IST)
    upcoming = [r for r in rounds if r.status == "scheduled" and r.scheduled_at and r.scheduled_at >= now]
    out: dict[str, Any] = {
        "id": a.id, "job_id": a.job_id, "company": a.company, "title": a.title, "url": a.url,
        "channel": a.channel, "resume_version": a.resume_version, "status": a.status,
        "applied_at": a.applied_at, "follow_up_on": a.follow_up_on, "notes": a.notes, "updated_at": a.updated_at,
        "follow_up_due": a.status in WAITING and a.follow_up_on is not None and a.follow_up_on <= date.today(),
        "rounds_total": len(rounds),
        "rounds_cleared": sum(r.status == "cleared" for r in rounds),
        "next_round": _round_out(min(upcoming, key=lambda r: r.scheduled_at)) if upcoming else None,
    }
    if detail:
        out["rounds"] = [_round_out(r) for r in rounds]
        out["emails"] = [_email_out(e) for e in session.scalars(
            select(Email).where(Email.application_id == a.id).order_by(Email.received_at.desc())
        )]
        out["events"] = [
            {"id": e.id, "from_status": e.from_status, "to_status": e.to_status, "evidence_type": e.evidence_type,
             "evidence_ref": e.evidence_ref, "note": e.note, "at": e.at}
            for e in session.scalars(
                select(StatusEvent).where(StatusEvent.application_id == a.id).order_by(StatusEvent.id)
            )
        ]
    return out


def _get(session: Session, app_id: int) -> Application:
    a = session.get(Application, app_id)
    if a is None:
        raise HTTPException(404, "application not found")
    return a


def _set_status(session: Session, a: Application, to: str, note: str | None = None,
                evidence_type: str = "user_action", evidence_ref: str | None = None) -> None:
    if a.status == to:
        return
    session.add(StatusEvent(application_id=a.id, from_status=a.status, to_status=to, note=note,
                            evidence_type=evidence_type, evidence_ref=evidence_ref))
    audit.record(session, "user", "application.status", f"application:{a.id}", from_status=a.status, to_status=to)
    a.status = to


@router.get("/applications/meta")
def applications_meta(session: Session = Depends(get_session)) -> dict[str, Any]:
    main = Path(prefs.get_section(session, "documents").main_resume_path).name
    return {
        "statuses": STATUS_LABELS, "channels": CHANNELS,
        "round_types": {k: {"label": label, "coach_round": c} for k, (label, c) in ROUND_TYPES.items()},
        "round_statuses": ROUND_STATUS_LABELS, "round_modes": list(ROUND_MODES),
        "resume_versions": _resume_versions(main), "main_resume": main,
    }


@router.get("/applications")
def list_applications(status: str | None = None, job_id: int | None = None,
                      session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    stmt = select(Application).order_by(Application.applied_at.desc(), Application.id.desc())
    if status:
        stmt = stmt.where(Application.status == status)
    if job_id is not None:
        stmt = stmt.where(Application.job_id == job_id)
    return [_app_out(session, a) for a in session.scalars(stmt)]


class ApplicationIn(BaseModel):
    job_id: int | None = None
    company: str | None = Field(None, max_length=200)
    title: str | None = Field(None, max_length=300)
    url: str | None = None
    channel: Literal[tuple(CHANNELS)] = "company_site"  # type: ignore[valid-type]
    resume_version: str | None = Field(None, max_length=200)
    applied_at: date | None = None
    follow_up_on: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def needs_job_or_names(self) -> "ApplicationIn":
        if self.job_id is None and not (self.company and self.company.strip() and self.title and self.title.strip()):
            raise ValueError("pick a job from JobPilot, or give the company and role")
        return self


@router.post("/applications", status_code=201)
def create_application(body: ApplicationIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    company, title, url = (body.company or "").strip(), (body.title or "").strip(), body.url
    if body.job_id is not None:
        job = session.get(Job, body.job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        existing = session.scalar(select(Application.id).where(Application.job_id == job.id))
        if existing is not None:
            raise HTTPException(409, f"you already logged an application for this job (#{existing})")
        company = company or session.get(Company, job.company_id).name
        title = title or job.title
        url = url or job.apply_url or job.url
    applied_at = body.applied_at or date.today()
    a = Application(
        job_id=body.job_id, company=company, title=title, url=url, channel=body.channel,
        resume_version=body.resume_version, status="applied", applied_at=applied_at,
        follow_up_on=body.follow_up_on or applied_at + timedelta(days=FOLLOW_UP_DAYS), notes=body.notes,
    )
    session.add(a)
    session.flush()
    session.add(StatusEvent(application_id=a.id, from_status=None, to_status="applied", note="Logged by you"))
    audit.record(session, "user", "application.created", f"application:{a.id}", company=company, title=title)
    return _app_out(session, a, detail=True)


@router.get("/applications/{app_id}")
def get_application(app_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _app_out(session, _get(session, app_id), detail=True)


class ApplicationPatch(BaseModel):
    status: Literal[APPLICATION_STATUSES] | None = None  # type: ignore[valid-type]
    status_note: str | None = None
    company: str | None = Field(None, min_length=1, max_length=200)
    title: str | None = Field(None, min_length=1, max_length=300)
    url: str | None = None
    channel: Literal[tuple(CHANNELS)] | None = None  # type: ignore[valid-type]
    resume_version: str | None = None
    applied_at: date | None = None
    follow_up_on: date | None = None
    notes: str | None = None


@router.patch("/applications/{app_id}")
def update_application(app_id: int, body: ApplicationPatch, session: Session = Depends(get_session)) -> dict[str, Any]:
    a = _get(session, app_id)
    fields = body.model_dump(exclude_unset=True)
    status, note = fields.pop("status", None), fields.pop("status_note", None)
    for k, v in fields.items():
        setattr(a, k, v)
    if status:
        _set_status(session, a, status, note)
    session.flush()
    return _app_out(session, a, detail=True)


@router.delete("/applications/{app_id}", status_code=204)
def delete_application(app_id: int, session: Session = Depends(get_session)) -> None:
    a = _get(session, app_id)
    audit.record(session, "user", "application.deleted", f"application:{a.id}", company=a.company, title=a.title)
    session.delete(a)
    session.flush()


class RoundIn(BaseModel):
    round_type: Literal[tuple(ROUND_TYPES)]  # type: ignore[valid-type]
    round_no: int | None = Field(None, ge=1)
    label: str | None = Field(None, max_length=200)
    scheduled_at: datetime | None = None
    mode: Literal[ROUND_MODES] | None = None  # type: ignore[valid-type]
    interviewer: str | None = Field(None, max_length=200)
    status: Literal[ROUND_STATUSES] = "scheduled"  # type: ignore[valid-type]
    questions: str | None = None
    feedback: str | None = None
    self_rating: int | None = Field(None, ge=1, le=5)


@router.post("/applications/{app_id}/rounds", status_code=201)
def add_round(app_id: int, body: RoundIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    a = _get(session, app_id)
    round_no = body.round_no
    if round_no is None:
        round_no = (session.scalar(
            select(func.max(InterviewRound.round_no)).where(InterviewRound.application_id == a.id)
        ) or 0) + 1
    elif session.scalar(select(InterviewRound.id).where(
            InterviewRound.application_id == a.id, InterviewRound.round_no == round_no)):
        raise HTTPException(409, f"round {round_no} already exists")
    r = InterviewRound(application_id=a.id, **{**body.model_dump(), "round_no": round_no,
                                               "scheduled_at": _as_ist(body.scheduled_at)})
    session.add(r)
    if a.status in BEFORE_INTERVIEWS:
        _set_status(session, a, "interviewing", f"Round {round_no} added")
    session.flush()
    audit.record(session, "user", "round.added", f"application:{a.id}", round_no=round_no, round_type=r.round_type)
    return _app_out(session, a, detail=True)


class RoundPatch(BaseModel):
    round_type: Literal[tuple(ROUND_TYPES)] | None = None  # type: ignore[valid-type]
    label: str | None = Field(None, max_length=200)
    scheduled_at: datetime | None = None
    mode: Literal[ROUND_MODES] | None = None  # type: ignore[valid-type]
    interviewer: str | None = Field(None, max_length=200)
    status: Literal[ROUND_STATUSES] | None = None  # type: ignore[valid-type]
    questions: str | None = None
    feedback: str | None = None
    self_rating: int | None = Field(None, ge=1, le=5)


def _get_round(session: Session, round_id: int) -> InterviewRound:
    r = session.get(InterviewRound, round_id)
    if r is None:
        raise HTTPException(404, "round not found")
    return r


@router.patch("/rounds/{round_id}")
def update_round(round_id: int, body: RoundPatch, session: Session = Depends(get_session)) -> dict[str, Any]:
    r = _get_round(session, round_id)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("status") is None:
        fields.pop("status", None)  # status can't be cleared, only changed
    if "scheduled_at" in fields:
        fields["scheduled_at"] = _as_ist(fields["scheduled_at"])
    for k, v in fields.items():
        setattr(r, k, v)
    session.flush()
    return _app_out(session, _get(session, r.application_id), detail=True)


@router.delete("/rounds/{round_id}")
def delete_round(round_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    r = _get_round(session, round_id)
    app_id = r.application_id
    audit.record(session, "user", "round.deleted", f"application:{app_id}", round_no=r.round_no)
    session.delete(r)
    session.flush()
    return _app_out(session, _get(session, app_id), detail=True)


# ---------- emails found by the inbox check ----------

def _email_out(e: Email) -> dict[str, Any]:
    return {
        "id": e.id, "gmail_msg_id": e.gmail_msg_id, "thread_id": e.thread_id, "application_id": e.application_id,
        "category": e.category, "sender": e.sender, "subject": e.subject, "summary": e.summary,
        "needs_reply": e.needs_reply, "handled": e.handled, "view_url": e.view_url, "received_at": e.received_at,
    }


@router.get("/emails/seen")
def emails_seen(ids: str, session: Session = Depends(get_session)) -> list[str]:
    """Which of these Gmail message ids were already handled. Lets the inbox check skip them."""
    wanted = [i for i in ids.split(",") if i]
    return list(session.scalars(select(Email.gmail_msg_id).where(Email.gmail_msg_id.in_(wanted))))


@router.get("/emails")
def list_emails(pending: bool = False, limit: int = 50, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    stmt = select(Email).order_by(Email.received_at.desc()).limit(limit)
    if pending:
        stmt = stmt.where(Email.needs_reply.is_(True), Email.handled.is_(False))
    rows = list(session.scalars(stmt))
    apps = {a.id: a for a in session.scalars(select(Application).where(
        Application.id.in_([e.application_id for e in rows if e.application_id])))}
    return [{**_email_out(e), "application": (
        {"id": apps[e.application_id].id, "company": apps[e.application_id].company, "title": apps[e.application_id].title}
        if e.application_id in apps else None)} for e in rows]


class NewFromEmail(BaseModel):
    job_id: int | None = None  # set when the role is already in JobPilot
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    url: str | None = None
    channel: Literal[tuple(CHANNELS)] = "company_site"  # type: ignore[valid-type]


class EmailIn(BaseModel):
    gmail_msg_id: str = Field(min_length=1, max_length=100)
    thread_id: str | None = Field(None, max_length=100)
    category: Literal[EMAIL_CATEGORIES]  # type: ignore[valid-type]
    sender: str = Field(min_length=1, max_length=300)
    subject: str = ""
    summary: str = Field("", max_length=1000)
    needs_reply: bool = False
    view_url: str | None = None
    received_at: datetime
    application_id: int | None = None
    new_application: NewFromEmail | None = None
    set_status: Literal[APPLICATION_STATUSES] | None = None  # type: ignore[valid-type]


@router.post("/emails")
def record_email(body: EmailIn, session: Session = Depends(get_session)) -> Any:
    """Record one email and, with the email as evidence, link or create the application and move its status.

    Idempotent on the Gmail message id, so a repeated check changes nothing.
    """
    existing = session.scalar(select(Email).where(Email.gmail_msg_id == body.gmail_msg_id))
    if existing is not None:
        return {"duplicate": True, "email": _email_out(existing)}

    app: Application | None = None
    if body.application_id is not None:
        app = _get(session, body.application_id)
    elif body.thread_id:
        # A reply in a thread we already linked belongs to the same application.
        linked = session.scalar(select(Email.application_id).where(
            Email.thread_id == body.thread_id, Email.application_id.is_not(None)))
        app = session.get(Application, linked) if linked else None
    if app is None and body.new_application is not None and body.new_application.job_id is not None:
        # Already logged for this job (by you, or by an earlier email): link to it.
        app = session.scalar(select(Application).where(Application.job_id == body.new_application.job_id))
        if app is None and session.get(Job, body.new_application.job_id) is None:
            raise HTTPException(404, "job not found")
    if app is None and body.new_application is not None:
        n = body.new_application
        applied_at = _as_ist(body.received_at).astimezone(IST).date()
        job = session.get(Job, n.job_id) if n.job_id else None
        app = Application(job_id=n.job_id, company=n.company.strip(), title=n.title.strip(),
                          url=n.url or (job.apply_url or job.url if job else None), channel=n.channel,
                          status="applied", applied_at=applied_at,
                          follow_up_on=applied_at + timedelta(days=FOLLOW_UP_DAYS))
        session.add(app)
        session.flush()
        session.add(StatusEvent(application_id=app.id, from_status=None, to_status="applied",
                                evidence_type="email", evidence_ref=body.gmail_msg_id,
                                note=f"Confirmation email from {body.sender}"))
        audit.record(session, "inbox-check", "application.created", f"application:{app.id}",
                     company=app.company, title=app.title, gmail_msg_id=body.gmail_msg_id)

    e = Email(gmail_msg_id=body.gmail_msg_id, thread_id=body.thread_id, application_id=app.id if app else None,
              category=body.category, sender=body.sender, subject=body.subject, summary=body.summary,
              needs_reply=body.needs_reply, view_url=body.view_url, received_at=_as_ist(body.received_at))
    session.add(e)
    if app is not None and body.set_status and body.set_status != "applied":
        _set_status(session, app, body.set_status, f"Email from {body.sender}: {body.subject}"[:500],
                    evidence_type="email", evidence_ref=body.gmail_msg_id)
    session.flush()
    return JSONResponse({"duplicate": False, "email": jsonable_encoder(_email_out(e)),
                         "application_id": app.id if app else None}, status_code=201)


class EmailPatch(BaseModel):
    handled: bool | None = None
    application_id: int | None = None


@router.patch("/emails/{email_id}")
def update_email(email_id: int, body: EmailPatch, session: Session = Depends(get_session)) -> dict[str, Any]:
    e = session.get(Email, email_id)
    if e is None:
        raise HTTPException(404, "email not found")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("application_id") is not None:
        _get(session, fields["application_id"])
    for k, v in fields.items():
        setattr(e, k, v)
    session.flush()
    return _email_out(e)
