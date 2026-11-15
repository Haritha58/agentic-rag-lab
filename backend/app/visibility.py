"""Which open jobs are worth showing: recent postings, plus anything you're already tracking."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import prefs
from app.models import Application, Job


def cutoff(session: Session, now: datetime | None = None) -> datetime:
    days = prefs.get_section(session, "discovery").max_posting_age_days
    return (now or datetime.now(timezone.utc)) - timedelta(days=days)


def fresh_or_tracked(session: Session) -> Any:
    """SQL condition: posted within the age limit, or shortlisted, or applied to."""
    posted = func.coalesce(Job.posted_at, Job.first_seen_at)
    applied = select(Application.job_id).where(Application.job_id.is_not(None))
    return (posted >= cutoff(session)) | (Job.user_status == "shortlisted") | Job.id.in_(applied)
