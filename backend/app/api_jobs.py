"""Jobs, companies, discovery runs and overview counts."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import audit, prefs, scoring, visibility
from app.db import get_session
from app.discovery import pipeline
from app.models import Application, Company, DiscoveryRun, Job, JobScore

router = APIRouter(prefix="/api")

SOURCE_LABELS = {
    "greenhouse": "Company careers (Greenhouse)", "lever": "Company careers (Lever)",
    "ashby": "Company careers (Ashby)", "smartrecruiters": "Company careers (SmartRecruiters)",
    "remotive": "Remotive", "remoteok": "Remote OK", "arbeitnow": "Arbeitnow", "himalayas": "Himalayas",
}


def job_summary(job: Job, company: Company, score: JobScore | None) -> dict[str, Any]:
    return {
        "id": job.id, "title": job.title, "company": company.name, "company_id": company.id,
        "category": company.category, "category_source": company.category_source, "size_band": company.size_band,
        "wlb_rating": company.wlb_rating, "segment": job.segment, "arrangement": job.arrangement,
        "location": job.location_raw, "cities": job.cities, "countries": job.countries,
        "role_family": job.role_family, "seniority": job.seniority, "exp_min": job.exp_min, "exp_max": job.exp_max,
        "salary": job.salary, "posted_at": job.posted_at, "first_seen_at": job.first_seen_at,
        "status": job.status, "user_status": job.user_status, "url": job.url, "apply_url": job.apply_url,
        "source": job.source, "source_label": SOURCE_LABELS.get(job.source, job.source),
        "suitability": score.suitability if score else None, "opportunity": score.opportunity if score else None,
        "readiness": score.readiness if score else None, "data_coverage": score.data_coverage if score else None,
        "difficulty": score.difficulty if score else None, "recommendation": score.recommendation if score else None,
    }


def freshness(posted: Any) -> Any:
    """Weight from 1.0 (posted in the last 3 days) down to 0.2 (over 60 days old)."""
    age = func.now() - posted
    return case(
        (age <= timedelta(days=3), 1.0), (age <= timedelta(days=7), 0.9), (age <= timedelta(days=14), 0.75),
        (age <= timedelta(days=30), 0.6), (age <= timedelta(days=60), 0.4), else_=0.2,
    )


@router.get("/jobs")
def list_jobs(
    session: Session = Depends(get_session),
    segment: str | None = None,
    role_family: str | None = None,
    category: int | None = Query(None, ge=0, le=3, description="0 = uncategorized"),
    arrangement: str | None = None,
    difficulty: str | None = None,
    user_status: str | None = "new",
    min_suitability: int = 0,
    min_salary_lpa: float | None = None,
    hide_below_floor: bool = True,
    posted_within_days: int | None = None,
    q: str | None = None,
    sort: Literal["fresh", "opportunity", "suitability", "posted", "oldest", "salary"] = "opportunity",
    limit: int = Query(200, le=1000),
) -> dict[str, Any]:
    stmt = (
        select(Job, Company, JobScore)
        .join(Company, Job.company_id == Company.id)
        .outerjoin(JobScore, JobScore.job_id == Job.id)
        .where(Job.status == "open", visibility.fresh_or_tracked(session))
    )
    if segment:
        stmt = stmt.where(Job.segment == segment)
    if role_family:
        stmt = stmt.where(Job.role_family == role_family)
    if category is not None:
        stmt = stmt.where(Company.category.is_(None) if category == 0 else Company.category == category)
    if arrangement:
        stmt = stmt.where(Job.arrangement == arrangement)
    if difficulty:
        stmt = stmt.where(JobScore.difficulty == difficulty)
    if user_status and user_status != "all":
        stmt = stmt.where(Job.user_status == user_status)
    if min_suitability:
        stmt = stmt.where(JobScore.suitability >= min_suitability)
    inr_max = Job.salary["inr_max"].as_float()
    if min_salary_lpa is not None:
        stmt = stmt.where(inr_max >= min_salary_lpa * 100_000)
    if hide_below_floor:
        floor = prefs.get_section(session, "compensation").hide_below_lpa
        # Only hides jobs whose *posted* pay is below the floor; undisclosed pay stays visible.
        stmt = stmt.where((inr_max.is_(None)) | (inr_max >= floor * 100_000))
    if posted_within_days:
        since = datetime.now(timezone.utc) - timedelta(days=posted_within_days)
        stmt = stmt.where(func.coalesce(Job.posted_at, Job.first_seen_at) >= since)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Job.title.ilike(like) | Company.name.ilike(like))
    posted = func.coalesce(Job.posted_at, Job.first_seen_at)
    order = {
        # Recruiters see early applicants first, so a good fit posted this week beats a slightly
        # better fit posted two months ago.
        "fresh": (func.coalesce(JobScore.opportunity, 0) * freshness(posted)).desc(),
        "opportunity": JobScore.opportunity.desc().nulls_last(),
        "suitability": JobScore.suitability.desc().nulls_last(),
        "posted": posted.desc(),
        "oldest": posted.asc(),
        "salary": inr_max.desc().nulls_last(),
    }[sort]
    rows = session.execute(stmt.order_by(order, Job.id).limit(limit)).all()
    # Tab badges use the same visibility rules as the default list, so the numbers match what you see.
    floor = prefs.get_section(session, "compensation").hide_below_lpa
    counts = dict(session.execute(
        select(Job.segment, func.count())
        .where(Job.status == "open", Job.user_status == "new", visibility.fresh_or_tracked(session),
               (inr_max.is_(None)) | (inr_max >= floor * 100_000))
        .group_by(Job.segment)
    ).all())
    applied = set(session.scalars(select(Application.job_id).where(Application.job_id.in_([r[0].id for r in rows]))))
    return {"jobs": [{**job_summary(*r), "applied": r[0].id in applied} for r in rows], "segment_counts": counts}


@router.get("/jobs/top-picks")
def get_top_picks(n: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [{**job_summary(job, company, score), "pick_reason": reason}
            for job, company, score, reason in scoring.top_picks(session, n)]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    company = session.get(Company, job.company_id)
    score = session.get(JobScore, job_id)
    detail = job_summary(job, company, score)
    detail.update(description=job.description, evidence=job.evidence, skills=job.skills)
    if score:
        detail.update(
            suitability_breakdown=score.suitability_breakdown, opportunity_breakdown=score.opportunity_breakdown,
            difficulty_evidence=score.difficulty_evidence, existing_skills=score.existing_skills,
            learning_skills=score.learning_skills, missing_skills=score.missing_skills,
            rejection_risks=score.rejection_risks, scored_at=score.scored_at, score_method=score.method,
            readiness_breakdown=score.readiness_breakdown,
        )
    return detail


class JobPatch(BaseModel):
    user_status: Literal["new", "shortlisted", "skipped"]


@router.patch("/jobs/{job_id}")
def patch_job(job_id: int, body: JobPatch, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    job.user_status = body.user_status
    audit.record(session, "user", f"job.{body.user_status}", f"job:{job_id}", title=job.title)
    return {"id": job_id, "user_status": job.user_status}


# ---------- companies ----------

@router.get("/companies")
def list_companies(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    open_jobs = (
        select(Job.company_id, func.count().label("n"))
        .where(Job.status == "open", visibility.fresh_or_tracked(session)).group_by(Job.company_id).subquery()
    )
    rows = session.execute(
        select(Company, func.coalesce(open_jobs.c.n, 0))
        .outerjoin(open_jobs, open_jobs.c.company_id == Company.id)
        .where((Company.on_watchlist.is_(True)) | (open_jobs.c.n > 0))
        .order_by(Company.category.nulls_last(), Company.name)
    ).all()
    return [
        {"id": c.id, "name": c.name, "category": c.category, "category_source": c.category_source,
         "size_band": c.size_band, "size_source": c.size_source, "ats": c.ats, "on_watchlist": c.on_watchlist,
         "wlb_rating": c.wlb_rating, "open_jobs": n}
        for c, n in rows
    ]


class CompanyPatch(BaseModel):
    category: Literal[1, 2, 3] | None = None
    size_band: str | None = None


@router.patch("/companies/{company_id}")
def patch_company(company_id: int, body: CompanyPatch, session: Session = Depends(get_session)) -> dict[str, Any]:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    if "category" in body.model_fields_set:
        company.category, company.category_source = body.category, "user"
    if "size_band" in body.model_fields_set:
        company.size_band, company.size_source = body.size_band, "user"
    audit.record(session, "user", "company.update", f"company:{company_id}", **body.model_dump(exclude_unset=True))
    session.flush()
    pipeline.rescore_all(session)  # category feeds difficulty and top picks
    return {"id": company.id, "category": company.category, "size_band": company.size_band}


# ---------- discovery runs & overview ----------

def run_out(run: DiscoveryRun) -> dict[str, Any]:
    return {"id": run.id, "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at,
            "stats": {k: v for k, v in (run.stats or {}).items() if k != "per_feed"}, "errors": run.errors}


@router.post("/discovery/run", status_code=202)
def trigger_run() -> dict[str, Any]:
    run = pipeline.start_background_run()
    if run is None:
        raise HTTPException(409, "a discovery run is already in progress")
    return run_out(run)


@router.get("/discovery/runs")
def list_runs(session: Session = Depends(get_session), limit: int = 10) -> list[dict[str, Any]]:
    runs = session.scalars(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(limit))
    return [run_out(r) for r in runs]


@router.post("/scores/recompute")
def recompute(session: Session = Depends(get_session)) -> dict[str, int]:
    """Re-score after editing settings or facts, without refetching jobs."""
    return {"scored": pipeline.rescore_all(session)}


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict[str, Any]:
    def count(*where) -> int:
        return session.scalar(select(func.count()).select_from(Job).where(*where)) or 0

    return {
        "discovered": count(Job.status == "open", visibility.fresh_or_tracked(session)),
        "max_posting_age_days": prefs.get_section(session, "discovery").max_posting_age_days,
        "shortlisted": count(Job.user_status == "shortlisted", Job.status == "open"),
        "new_last_24h": count(Job.first_seen_at >= datetime.now(timezone.utc) - timedelta(hours=24)),
        # Later phases fill these in.
        "awaiting_approval": 0, "applied": 0, "recruiter_replies": 0, "assessments": 0,
        "interviews": 0, "offers": 0, "rejections": 0,
    }
