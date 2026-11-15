"""Discovery run: fetch feeds -> classify -> dedupe/upsert -> expire -> score."""

import concurrent.futures as cf
import hashlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app import audit, prep, scoring, visibility
from app.db import session_factory
from app.discovery import fx
from app.discovery.classify import experience_range, place, role_family, seniority
from app.discovery.salary import from_text, with_inr
from app.discovery.skills import extract_skills
from app.discovery.sources import FETCHERS, Feed, Http, RawJob, board_feeds
from app.discovery.text import norm
from app.models import Company, DiscoveryRun, Job, JobScore, JobSource

log = logging.getLogger(__name__)
WATCHLIST = Path(__file__).with_name("watchlist.yaml")
_run_lock = threading.Lock()


def seed_watchlist(session: Session, path: Path = WATCHLIST) -> int:
    entries = yaml.safe_load(path.read_text())["companies"]
    for e in entries:
        company = company_for(session, e["name"])
        company.on_watchlist = True
        company.ats, company.ats_slug = e["ats"], e["slug"]
        if company.category_source != "user":  # never overwrite your own override
            company.category, company.category_source = e["category"], "curated_estimate"
        if e.get("size_band") and company.size_source != "user":
            company.size_band, company.size_source = e["size_band"], "curated_estimate"
    session.flush()
    return len(entries)


def company_for(session: Session, name: str) -> Company:
    key = norm(name) or "unknown"
    company = session.scalar(select(Company).where(Company.key == key))
    if company is None:
        company = Company(name=name.strip() or "Unknown", key=key, category_source="unknown",
                          size_source="unknown", wlb_rating="insufficient", wlb_evidence=[], stability={})
        session.add(company)
        session.flush()
    return company


def watchlist_feeds(session: Session) -> list[Feed]:
    companies = session.scalars(select(Company).where(Company.on_watchlist.is_(True), Company.ats.is_not(None)))
    return [Feed(f"{c.ats}:{c.ats_slug}", FETCHERS[c.ats](c.name, c.ats_slug)) for c in companies if c.ats in FETCHERS]


def _dedupe_key(company: Company, title: str, segment: str, cities: list[str]) -> str:
    raw = f"{company.key}|{norm(title)}|{segment}|{cities[0] if cities else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def ingest(session: Session, raw: RawJob, feed: str, now: datetime, rates: dict[str, float], fx_date: str | None,
           too_old_before: datetime | None = None) -> str:
    family = role_family(raw.title, raw.description)
    if family is None:
        return "skipped_role"
    placement = place(raw.location, raw.description, raw.hints)
    if placement.segment is None:
        # A job stored earlier that the current rules rule out (e.g. remote for US/Canada only) leaves the list.
        link = session.get(JobSource, (raw.source, raw.source_job_id))
        job = session.get(Job, link.job_id) if link is not None else None
        if job is None:
            return "skipped_location"
        link.last_seen_at = now
        job.last_seen_at = now
        if job.status != "open":
            return "skipped_location"
        job.status = "ineligible"
        job.evidence = {**placement.evidence, "eligibility": placement.eligibility} if placement.eligibility else placement.evidence
        return "now_ineligible"

    company = company_for(session, raw.company_name)
    exp_min, exp_max = experience_range(raw.description)
    salary = with_inr(raw.salary or from_text(raw.description), rates, fx_date)
    expired = raw.expires_at is not None and raw.expires_at < now
    fields: dict[str, Any] = dict(
        title=raw.title[:300], role_family=family, seniority=seniority(raw.title),
        description=raw.description, location_raw=raw.location, countries=placement.countries,
        cities=placement.cities, arrangement=placement.arrangement, segment=placement.segment,
        evidence={**placement.evidence, "eligibility": placement.eligibility} if placement.eligibility else placement.evidence,
        exp_min=exp_min, exp_max=exp_max, skills=extract_skills(f"{raw.title}\n{raw.description}"),
        last_seen_at=now, status="expired" if expired else "open",
    )

    link = session.get(JobSource, (raw.source, raw.source_job_id))
    if link is not None:
        job = session.get(Job, link.job_id)
        for k, v in fields.items():
            setattr(job, k, v)
        if salary.get("provenance") != "not_disclosed":
            job.salary = salary
        link.last_seen_at = now
        return "updated"

    key = _dedupe_key(company, raw.title, placement.segment, placement.cities)
    job = session.scalar(select(Job).where(Job.dedupe_key == key))
    result = "duplicate"
    if job is None and too_old_before is not None and raw.posted_at is not None and raw.posted_at < too_old_before:
        # Long-open "evergreen" postings rarely get replies. Jobs already stored keep updating above.
        return "skipped_old"
    if job is None:
        job = Job(company_id=company.id, source=raw.source, url=raw.url, apply_url=raw.apply_url,
                  posted_at=raw.posted_at, first_seen_at=now, dedupe_key=key, salary=salary, user_status="new", **fields)
        session.add(job)
        session.flush()
        result = "new"
    else:
        job.last_seen_at = now
        if job.status == "expired" and not expired:
            job.status = "open"
    session.add(JobSource(source=raw.source, source_job_id=raw.source_job_id, job_id=job.id,
                          feed=feed, url=raw.url, last_seen_at=now))
    session.flush()  # the same posting can come back from another search feed in this run
    return result


def expire_missing(session: Session, complete_feeds: list[str], run_start: datetime) -> int:
    """Jobs from a complete feed that weren't seen this run (via any source) have closed."""
    if not complete_feeds:
        return 0
    stale = select(JobSource.job_id).where(JobSource.feed.in_(complete_feeds), JobSource.last_seen_at < run_start)
    result = session.execute(
        update(Job).where(Job.id.in_(stale), Job.last_seen_at < run_start, Job.status == "open").values(status="expired")
    )
    return result.rowcount


def rescore_all(session: Session) -> int:
    profile = scoring.load_profile(session)
    rows = session.execute(select(Job, Company).join(Company, Job.company_id == Company.id).where(Job.status == "open")).all()
    session.execute(delete(JobScore))
    for job, company in rows:
        session.add(scoring.score_job(job, company, profile, session))
    session.flush()
    prep.refresh_readiness(session)
    return len(rows)


def run_discovery(session: Session, feeds: list[Feed], http: Http, run: DiscoveryRun,
                  rates: tuple[dict[str, float], str | None] | None = None, workers: int = 6) -> DiscoveryRun:
    run_start = datetime.now(timezone.utc)
    rates_map, fx_date = rates if rates is not None else fx.get_rates(session, http.client)
    too_old = visibility.cutoff(session, run_start)
    stats: dict[str, Any] = {"feeds": len(feeds), "fetched": 0, "new": 0, "updated": 0, "duplicate": 0,
                             "skipped_role": 0, "skipped_location": 0, "skipped_old": 0, "now_ineligible": 0, "expired": 0, "per_feed": {}}
    errors: list[dict[str, str]] = []
    ok_complete: list[str] = []

    with cf.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(feed.fetch, http): feed for feed in feeds}
        for fut in cf.as_completed(futures):
            feed = futures[fut]
            try:
                raws = fut.result()
            except Exception as e:  # one broken feed must not stop the run
                log.warning("feed %s failed: %s", feed.name, e)
                errors.append({"feed": feed.name, "error": f"{e.__class__.__name__}: {e}"[:300]})
                continue
            counts: dict[str, int] = {}
            for raw in raws:
                outcome = ingest(session, raw, feed.name, run_start, rates_map, fx_date, too_old)
                counts[outcome] = counts.get(outcome, 0) + 1
                stats[outcome] += 1
            stats["fetched"] += len(raws)
            stats["per_feed"][feed.name] = counts
            if feed.complete:
                ok_complete.append(feed.name)

    stats["expired"] = expire_missing(session, ok_complete, run_start)
    stats["scored"] = rescore_all(session)
    run.finished_at = datetime.now(timezone.utc)
    run.status = "done"
    run.stats = stats
    run.errors = errors
    audit.record(session, "system", "discovery.run", f"run:{run.id}",
                 new=stats["new"], expired=stats["expired"], errors=len(errors))
    return run


def start_background_run() -> DiscoveryRun | None:
    """Kick off a full discovery run in a thread. Returns None if one is already running."""
    if not _run_lock.acquire(blocking=False):
        return None
    with session_factory()() as s:
        run = DiscoveryRun(status="running", stats={}, errors=[])
        s.add(run)
        s.commit()
        run_id = run.id

    def work() -> None:
        http = Http()
        try:
            with session_factory()() as s:
                run = s.get(DiscoveryRun, run_id)
                try:
                    seed_watchlist(s)
                    run_discovery(s, watchlist_feeds(s) + board_feeds(), http, run)
                    s.commit()
                except Exception as e:
                    log.exception("discovery run failed")
                    s.rollback()
                    run = s.get(DiscoveryRun, run_id)
                    run.status, run.finished_at = "failed", datetime.now(timezone.utc)
                    run.errors = [{"feed": "*", "error": f"{e.__class__.__name__}: {e}"[:500]}]
                    s.commit()
        finally:
            http.close()
            _run_lock.release()

    threading.Thread(target=work, name=f"discovery-{run_id}", daemon=True).start()
    return run
