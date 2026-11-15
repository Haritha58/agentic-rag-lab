"""Rule-based job scoring (Phase 2). The LLM refines this later; these rules stay as the baseline.

Three separate outputs, never merged:
- suitability: how well the job fits you
- opportunity: the ranking score (your 7 weighted factors)
- readiness: how ready you are for its interviews (computed in app.prep from coach scores)

Any factor without real data gets the configured floor (default 30): missing
information can lower a score but never raise it.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import prefs, visibility
from app.discovery.skills import AI_SKILLS, TRANSFERABLE, extract_skills
from app.models import Company, Employment, Job, JobScore, ProfileFact

AI_FAMILIES = {"ai_engineer", "ai_backend"}
DIFFICULTY_LEVELS = ["beginner_friendly", "medium", "difficult", "highly_competitive"]
_ADVANCED_DEGREE = re.compile(r"\b(master'?s|m\.?s\.?|ph\.?d|doctorate)\b[^.]{0,40}\b(required|must)\b|\brequire[sd]? (?:a )?(master'?s|ph\.?d)", re.IGNORECASE)
_PHD = re.compile(r"\bph\.?d\b[^.]{0,40}\b(required|must)\b", re.IGNORECASE)


@dataclass
class Profile:
    professional: set[str] = field(default_factory=set)
    learning: set[str] = field(default_factory=set)
    unconfirmed: set[str] = field(default_factory=set)
    years: float = 0.0


def load_profile(session: Session) -> Profile:
    p = Profile()
    for f in session.scalars(select(ProfileFact)):
        skills = set(extract_skills(f.text + " " + " ".join(f.skills)))
        if f.kind == "professional" and not f.needs_confirmation:
            p.professional |= skills
        elif f.kind == "professional":
            p.unconfirmed |= skills
        elif f.kind in ("learning", "personal_project", "certification"):
            p.learning |= skills
    p.learning -= p.professional
    p.unconfirmed -= p.professional
    starts = [e.start for e in session.scalars(select(Employment))]
    if starts:
        y, m = map(int, min(starts).split("-"))
        today = date.today()
        p.years = round((today.year - y) + (today.month - m) / 12, 1)
    return p


def _part(score: float | None, weight: int, note: str, floor: int) -> dict[str, Any]:
    known = score is not None
    return {"score": round(score) if known else floor, "weight": weight, "known": known, "note": note}


def _weighted(parts: dict[str, dict[str, Any]]) -> int:
    total = sum(p["weight"] for p in parts.values()) or 1
    return round(sum(p["score"] * p["weight"] for p in parts.values()) / total)


def location_fit(job: Job, home_city: str = "") -> tuple[float | None, str]:
    if job.segment == "IN_REMOTE":
        if job.arrangement == "remote_city_restricted":
            return (100, f"Remote, limited to {home_city}") if home_city in job.cities else (80, f"Remote but limited to {', '.join(job.cities)}")
        if job.arrangement == "remote_occasional_office":
            return 90, "Remote with occasional office visits"
        return 100, "Fully remote within India"
    if job.segment == "IN_ONSITE_HYBRID":
        if home_city in job.cities:
            return 100, f"In {home_city}"
        return 70, f"Needs presence in {', '.join(job.cities) or 'an Indian office'}"
    if job.segment == "INTL_REMOTE":
        return 90, "International remote, India eligibility verified"
    if job.segment == "INTL_RELOCATION":
        return 70, "Requires relocation abroad (visa sponsorship mentioned)"
    return None, "Eligibility not verified"


def compensation_fit(job: Job, comp: prefs.Compensation) -> tuple[float | None, str]:
    s = job.salary or {}
    if not s.get("inr_max"):
        return None, "Not disclosed"
    mid_lpa = (s["inr_min"] + s["inr_max"]) / 2 / 100_000
    target, soft, current = comp.target_lpa, comp.soft_floor_lpa, comp.current_total_lpa
    if mid_lpa >= target:
        score = 100
    elif mid_lpa >= soft:
        score = 60 + 40 * (mid_lpa - soft) / (target - soft)
    elif mid_lpa >= current:
        score = 20 + 40 * (mid_lpa - current) / (soft - current)
    else:
        score = 0
    note = f"~{mid_lpa:.0f} LPA midpoint (posted)"
    if job.segment == "INTL_RELOCATION":
        note += "; gross, not adjusted for tax or cost of living"
    return score, note


def difficulty(job: Job, company: Company) -> tuple[str, list[str]]:
    evidence = []
    if company.category == 3:
        level, evidence = 3, ["Highly competitive company (category 3)"]
    elif company.category in (1, 2):
        level = 1
        evidence.append(f"Company category {company.category}")
    else:
        level = 1
        evidence.append("Company category unknown; assumed medium")
    if "dsa" in job.skills:
        level = min(3, level + 1)
        evidence.append("Posting mentions data structures / algorithms")
    if job.seniority in ("staff", "principal"):
        level = min(3, level + 1)
        evidence.append(f"{job.seniority.title()}-level role")
    if level == 1 and company.category == 1 and "dsa" not in job.skills and (job.exp_min or 0) <= 5:
        level = 0
        evidence.append("Mid-sized company, no DSA emphasis in the posting")
    return DIFFICULTY_LEVELS[level], evidence


def score_job(job: Job, company: Company, profile: Profile, session: Session) -> JobScore:
    weights = prefs.get_section(session, "opportunity_weights")
    floor = prefs.get_section(session, "scoring").missing_data_floor
    comp = prefs.get_section(session, "compensation")

    jd = set(job.skills)
    have = sorted(jd & profile.professional)
    learning = sorted(jd & profile.learning)
    missing = sorted(jd - profile.professional - profile.learning)

    # ----- suitability -----
    if jd:
        tech = 100 * (len(have) + 0.4 * len(learning)) / len(jd)
        tech_note = f"{len(have)} of {len(jd)} skills from work experience, {len(learning)} from learning"
    else:
        tech, tech_note = None, "No recognizable skills in the posting"

    if job.exp_min is None:
        exp, exp_note = None, "Experience requirement not stated"
    else:
        hi = job.exp_max or job.exp_min + 6
        if profile.years < job.exp_min:
            exp = max(0, 100 - 25 * (job.exp_min - profile.years))
        elif profile.years > hi + 3:
            exp = 70
        else:
            exp = 100
        exp_note = f"Asks {job.exp_min}{'-' + str(job.exp_max) if job.exp_max else '+'} yrs; you have ~{profile.years:.0f}"
    if job.seniority == "junior":
        exp, exp_note = 40, "Junior-level title; likely below your experience"

    transfer = jd & TRANSFERABLE & profile.professional
    domain = min(100, 25 * len(transfer)) if jd else None
    direction = {"ai_engineer": 100, "ai_backend": 100, "java_backend": 60, "backend": 50}[job.role_family]
    loc_score, loc_note = location_fit(job, prefs.get_section(session, "segments").home_city)
    if _PHD.search(job.description):
        qual, qual_note = 20, "PhD required"
    elif _ADVANCED_DEGREE.search(job.description):
        qual, qual_note = 40, "Master's degree required"
    else:
        qual, qual_note = 100, "No advanced degree required"

    suit_parts = {
        "technical": _part(tech, 35, tech_note, floor),
        "experience": _part(exp, 15, exp_note, floor),
        "transferable": _part(domain, 15, ", ".join(sorted(transfer)) or "None matched", floor),
        "role_direction": _part(direction, 15, job.role_family.replace("_", " "), floor),
        "location": _part(loc_score, 10, loc_note, floor),
        "qualifications": _part(qual, 10, qual_note, floor),
    }
    suitability = _weighted(suit_parts)

    # ----- opportunity -----
    diff, diff_evidence = difficulty(job, company)
    wlb = {"excellent": 100, "good": 80, "average": 50, "poor": 15}.get(company.wlb_rating)
    stability = (company.stability or {}).get("score")
    ai_in_jd = len(jd & AI_SKILLS)
    growth = 90 if job.role_family in AI_FAMILIES else min(70, 40 + 10 * ai_in_jd)
    comp_score, comp_note = compensation_fit(job, comp)
    access = {"beginner_friendly": 100, "medium": 75, "difficult": 45, "highly_competitive": 20}[diff]

    w = weights
    opp_parts = {
        "technical_match": _part(suitability, w.technical_match, "Job suitability score", floor),
        "work_life_balance": _part(wlb, w.work_life_balance, f"Rating: {company.wlb_rating}", floor),
        "compensation": _part(comp_score, w.compensation, comp_note, floor),
        "company_stability": _part(stability, w.company_stability, "Not researched yet" if stability is None else "Researched", floor),
        "growth_ai_exposure": _part(growth, w.growth_ai_exposure, f"{ai_in_jd} AI skills in posting", floor),
        "arrangement_location": _part(loc_score, w.arrangement_location, loc_note, floor),
        "interview_accessibility": _part(access, w.interview_accessibility, diff.replace("_", " "), floor),
    }
    opportunity = _weighted(opp_parts)
    coverage = round(100 * sum(p["weight"] for p in opp_parts.values() if p["known"]) / 100)

    # ----- risks & recommendation -----
    risks = []
    if missing:
        risks.append(f"Missing skills: {', '.join(missing[:5])}")
    if job.role_family in AI_FAMILIES and jd & AI_SKILLS & profile.unconfirmed:
        risks.append("Your AI work experience is still unconfirmed in your profile, so it isn't counted yet")
    if job.exp_min and profile.years < job.exp_min:
        risks.append(f"Asks for {job.exp_min}+ years")
    if job.seniority in ("staff", "principal"):
        risks.append("Staff/principal level: expect a high system-design bar")
    if job.seniority == "junior":
        risks.append("Title suggests a junior role")
    if qual < 100:
        risks.append(qual_note)
    if job.posted_at and (datetime.now(timezone.utc) - job.posted_at).days > 30:
        risks.append("Posted over 30 days ago")

    if suitability >= 80:
        rec = "apply_now" if diff in ("beginner_friendly", "medium") else "prep_then_apply"
    elif suitability >= 60:
        rec = "prep_then_apply"
    elif suitability >= 45 and job.role_family in AI_FAMILIES:
        rec = "stretch"
    else:
        rec = "skip"

    return JobScore(
        job_id=job.id, method="rules", scored_at=datetime.now(timezone.utc),
        suitability=suitability, suitability_breakdown=suit_parts,
        opportunity=opportunity, opportunity_breakdown=opp_parts, data_coverage=coverage, readiness=None,
        difficulty=diff, difficulty_evidence=diff_evidence,
        existing_skills=have, learning_skills=learning, missing_skills=missing,
        rejection_risks=risks, recommendation=rec,
    )


def top_picks(session: Session, n: int = 10) -> list[tuple[Job, Company, JobScore, str]]:
    """Best open, un-actioned jobs, split across company categories by your allocation (default 60/30/10)."""
    alloc = prefs.get_section(session, "company_allocation")
    rows = session.execute(
        select(Job, Company, JobScore)
        .join(Company, Job.company_id == Company.id).join(JobScore, JobScore.job_id == Job.id)
        .where(Job.status == "open", Job.user_status == "new", Job.segment != "UNVERIFIED",
               JobScore.recommendation != "skip", visibility.fresh_or_tracked(session))
        .order_by(JobScore.opportunity.desc())
    ).all()
    quotas = {1: round(n * alloc.medium / 100), 2: round(n * alloc.large / 100), 3: round(n * alloc.highly_competitive / 100)}
    picked, used = [], set()
    for cat, quota in quotas.items():
        for job, company, score in rows:
            if quota == 0:
                break
            if company.category == cat and job.id not in used:
                picked.append((job, company, score, f"Category {cat} slot"))
                used.add(job.id)
                quota -= 1
    for job, company, score in rows:  # fill gaps (e.g. not enough category-3 jobs) with the best remaining
        if len(picked) >= n:
            break
        if job.id not in used:
            picked.append((job, company, score, "Best remaining"))
            used.add(job.id)
    return sorted(picked, key=lambda r: -r[2].opportunity)
