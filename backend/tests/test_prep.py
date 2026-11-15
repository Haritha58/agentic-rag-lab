from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import prep
from app.discovery.sources import Feed
from app.models import Job, JobScore, ProficiencyEvent, TopicSelfRating
from tests.test_pipeline import profile, raw, run  # noqa: F401 (profile is a fixture)


def ai_job(session) -> Job:
    run(session, [Feed("greenhouse:acme", lambda http: [raw(1)])])
    return session.scalar(select(Job))


def test_topic_weights_follow_the_jd(session):
    job = ai_job(session)
    weights = prep.topic_weights(job)
    assert sum(weights.values()) == 100
    assert {"rag", "python", "spring", "dsa", "system_design", "behavioral"} <= set(weights)
    assert weights["system_design"] > weights["behavioral"]  # senior role: design weighs more
    assert "ml_fundamentals" not in weights


def test_tooling_topics_are_capped(session):
    run(session, [Feed("greenhouse:acme", lambda http: [raw(1, description="AWS GCP Azure Docker Kubernetes Terraform Jenkins")])])
    weights = prep.topic_weights(session.scalar(select(Job)))
    assert weights["cloud_devops"] < weights["system_design"]


def test_proficiency_decays_and_uses_self_rating(session):
    now = datetime.now(timezone.utc)
    session.add_all([
        ProficiencyEvent(topic="rag", score=100, at=now - timedelta(days=60)),  # weight 0.25
        ProficiencyEvent(topic="rag", score=40, at=now),  # weight 1
        TopicSelfRating(topic="python", rating=3),
    ])
    session.flush()
    profs = prep.proficiencies(session, now)
    assert profs["rag"].score == 52 and profs["rag"].evidence == 2  # (25 + 40) / 1.25
    assert profs["python"].score == 60 and profs["python"].evidence == 0
    assert profs["dsa"].score is None


def test_readiness_is_none_without_evidence_and_uses_the_floor(session):
    job = ai_job(session)
    readiness, breakdown = prep.job_readiness(session, job)
    assert readiness is None and breakdown["coverage"] == 0
    assert len(breakdown["top_gaps"]) == 3 and breakdown["prep_hours_est"] > 0

    session.add(ProficiencyEvent(topic="rag", score=90))
    session.flush()
    readiness, breakdown = prep.job_readiness(session, job)
    rag_w = prep.topic_weights(job)["rag"]
    assert breakdown["coverage"] == rag_w
    assert readiness == round((rag_w * 90 + (100 - rag_w) * 30) / 100)  # unknown topics sit at the floor
    assert "rag" not in breakdown["top_gaps"]


def test_rescore_keeps_readiness(session):
    job = ai_job(session)
    session.add(ProficiencyEvent(topic="system_design", score=80))
    session.flush()
    from app.discovery import pipeline
    pipeline.rescore_all(session)
    score = session.get(JobScore, job.id)
    assert score.readiness is not None and score.readiness_breakdown["coverage"] > 0


def test_self_rating_endpoint(client, session):
    job = ai_job(session)
    out = client.put("/api/prep/topics/rag", json={"rating": 4}).json()
    assert out["score"] == 80 and out["self_rating"] == 4
    assert session.get(JobScore, job.id).readiness is not None
    assert client.put("/api/prep/topics/rag", json={"rating": None}).json()["score"] is None
    assert client.put("/api/prep/topics/nope", json={"rating": 1}).status_code == 404
    assert client.put("/api/prep/topics/rag", json={"rating": 9}).status_code == 422
    topics = {t["topic"] for t in client.get("/api/prep/topics").json()}
    assert topics == set(prep.TOPICS)
