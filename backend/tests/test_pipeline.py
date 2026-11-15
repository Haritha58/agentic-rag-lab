from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import prefs
from app.discovery import pipeline
from app.discovery.classify import LocationHints
from app.discovery.sources import Feed, RawJob
from app.models import Company, DiscoveryRun, Employment, Job, JobScore, JobSource, ProfileFact

AI_JD = (
    "Build RAG services in Python with embeddings and a vector database. 5+ years backend experience. "
    "Java and Spring Boot microservices on AWS a plus. Salary: 30 - 40 LPA."
)


def raw(i: int, **kw) -> RawJob:
    base = dict(source="greenhouse", source_job_id=str(i), company_name="Acme AI", title="Senior AI Engineer",
                url=f"https://example.com/{i}", location="Bengaluru, India", description=AI_JD)
    return RawJob(**{**base, **kw})


class FakeHttp:
    client = None


def run(session, feeds) -> DiscoveryRun:
    r = DiscoveryRun(status="running", stats={}, errors=[])
    session.add(r)
    session.flush()
    return pipeline.run_discovery(session, feeds, FakeHttp(), r, rates=({"USD": 94.0}, "2026-11-12"), workers=2)


@pytest.fixture
def profile(session):
    session.add(Employment(id="acme", company="Prev Co", start="2018-05"))
    session.flush()
    session.add_all([
        ProfileFact(id="f1", kind="professional", employer_id="acme", text="Java Spring Boot microservices on AWS SQS",
                    skills=["Java", "Spring Boot"], needs_confirmation=False),
        ProfileFact(id="f2", kind="professional", employer_id="acme", text="Built RAG pipelines with embeddings",
                    skills=["RAG"], needs_confirmation=True),
        ProfileFact(id="l1", kind="learning", text="Studying Python and vector databases", skills=["Python"]),
    ])
    session.flush()


def test_run_ingests_classifies_and_scores(session, profile):
    feeds = [Feed("greenhouse:acme", lambda http: [raw(1), raw(2, title="Account Executive"),
                                                   raw(3, location="Remote - US", title="Backend Engineer")])]
    result = run(session, feeds)
    assert result.status == "done"
    assert (result.stats["new"], result.stats["skipped_role"], result.stats["skipped_location"]) == (1, 1, 1)

    job = session.scalar(select(Job))
    assert (job.segment, job.role_family, job.salary["inr_min"]) == ("IN_ONSITE_HYBRID", "ai_engineer", 3_000_000)
    score = session.get(JobScore, job.id)
    assert "java" in score.existing_skills and "python" in score.learning_skills
    assert "rag" not in score.existing_skills  # unconfirmed facts don't count
    assert any("unconfirmed" in r for r in score.rejection_risks)
    assert score.readiness is None


def test_same_job_from_two_sources_is_one_row(session, profile):
    feeds = [
        Feed("greenhouse:acme", lambda http: [raw(1)]),
        Feed("himalayas:india:ai", lambda http: [raw(99, source="himalayas", url="https://h/99")], complete=False),
    ]
    run(session, feeds)
    assert session.scalar(select(func.count()).select_from(Job)) == 1
    assert session.scalar(select(func.count()).select_from(JobSource)) == 2


def test_rerun_updates_and_missing_jobs_expire(session, profile):
    run(session, [Feed("greenhouse:acme", lambda http: [raw(1), raw(2, title="Senior Java Developer")])])
    second = run(session, [Feed("greenhouse:acme", lambda http: [raw(1)])])
    assert second.stats["updated"] == 1 and second.stats["expired"] == 1
    statuses = dict(session.execute(select(Job.title, Job.status)).all())
    assert statuses == {"Senior AI Engineer": "open", "Senior Java Developer": "expired"}


def test_search_feed_absence_does_not_expire(session, profile):
    run(session, [Feed("himalayas:india:ai", lambda http: [raw(5, source="himalayas")], complete=False)])
    second = run(session, [Feed("himalayas:india:ai", lambda http: [], complete=False)])
    assert second.stats["expired"] == 0


def test_broken_feed_is_reported_not_fatal(session, profile):
    def boom(http):
        raise RuntimeError("board down")

    result = run(session, [Feed("lever:broken", boom), Feed("greenhouse:acme", lambda http: [raw(1)])])
    assert result.status == "done" and result.stats["new"] == 1
    assert result.errors[0]["feed"] == "lever:broken"


def test_unknown_data_never_raises_scores(session, profile):
    run(session, [Feed("greenhouse:acme", lambda http: [raw(1)])])
    score = session.scalar(select(JobScore))
    wlb = score.opportunity_breakdown["work_life_balance"]
    assert wlb["known"] is False and wlb["score"] == prefs.Scoring().missing_data_floor
    assert score.data_coverage < 100


def test_himalayas_expiry_date_marks_expired(session, profile):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    run(session, [Feed("himalayas:india:ai", lambda http: [raw(7, source="himalayas", expires_at=past)], complete=False)])
    assert session.scalar(select(Job.status)) == "expired"


def test_top_picks_follow_allocation(session, profile):
    feeds = [Feed("greenhouse:mix", lambda http: [
        raw(i, company_name=f"Co{i}", title="Senior AI Engineer") for i in range(1, 7)
    ])]
    run(session, feeds)
    for i, company in enumerate(session.scalars(select(Company).order_by(Company.name))):
        company.category = [1, 1, 1, 2, 2, 3][i]
    session.flush()
    pipeline.rescore_all(session)
    from app.scoring import top_picks
    picks = top_picks(session, n=5)
    cats = [c.category for _, c, _, _ in picks]
    assert cats.count(1) == 3 and cats.count(2) == 2 - 0 and len(picks) == 5


def test_seed_watchlist_keeps_user_category(session):
    pipeline.seed_watchlist(session)
    stripe = session.scalar(select(Company).where(Company.key == "stripe"))
    assert stripe.on_watchlist and stripe.category == 3 and stripe.category_source == "curated_estimate"
    stripe.category, stripe.category_source = 2, "user"
    pipeline.seed_watchlist(session)
    assert stripe.category == 2


def test_india_remote_from_lever_hints(session, profile):
    r = raw(8, source="lever", location="India", hints=LocationHints(remote=True, country_codes=["IN"]),
            title="Backend Engineer", description=AI_JD)
    run(session, [Feed("lever:acme", lambda http: [r])])
    job = session.scalar(select(Job))
    assert (job.segment, job.arrangement, job.role_family) == ("IN_REMOTE", "fully_remote", "ai_backend")



def test_discovery_skips_old_postings(session, profile):
    from datetime import datetime, timedelta, timezone

    old = datetime.now(timezone.utc) - timedelta(days=45)
    r = run(session, [Feed("greenhouse:acme", lambda http: [
        raw(1, posted_at=old), raw(2, title="Senior Java Developer", posted_at=datetime.now(timezone.utc)),
    ])])
    assert r.stats["skipped_old"] == 1 and r.stats["new"] == 1
    assert [j.title for j in session.scalars(select(Job))] == ["Senior Java Developer"]


def test_stored_job_that_becomes_ineligible_leaves_the_list(session, profile):
    worldwide = dict(location="Remote - Worldwide", description=AI_JD)
    run(session, [Feed("greenhouse:acme", lambda http: [raw(1, **worldwide)])])
    job = session.scalar(select(Job))
    assert (job.segment, job.status) == ("INTL_REMOTE", "open")

    us_only = dict(location="Remote - Worldwide", description=AI_JD + " This is a remote role for US / Canada based candidates.")
    r = run(session, [Feed("greenhouse:acme", lambda http: [raw(1, **us_only)])])
    assert r.stats["now_ineligible"] == 1
    session.refresh(job)
    assert job.status == "ineligible" and job.evidence["eligibility"]["india_eligible"] == "verified_no"
