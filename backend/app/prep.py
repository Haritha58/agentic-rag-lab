"""Interview readiness (Phase 5a), kept separate from suitability and opportunity.

readiness(job) = Σ topic_weight(job) × proficiency(topic)

- Topic weights come from the job's extracted skills plus rounds nearly every
  interview has (coding, system design, behavioral). Rules only, no LLM.
- Proficiency is a time-decayed average of the coach's rubric scores (half-life
  30 days), with your self-rating counted as one light prior.
- A topic with no evidence gets the missing-data floor, so readiness can't look
  better than the evidence. With no evidence on any of a job's topics,
  readiness stays None instead of showing a made-up number.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import prefs
from app.models import Job, JobScore, ProficiencyEvent, TopicSelfRating

# topic -> (label, skills from app.discovery.skills that point to it)
TOPICS: dict[str, tuple[str, set[str]]] = {
    "java_core": ("Java core & concurrency", {"java", "kotlin", "scala"}),
    "spring": ("Spring Boot & APIs", {"spring boot", "spring", "spring webflux", "hibernate", "rest apis", "grpc", "graphql", "oauth2"}),
    "distributed": ("Microservices & distributed systems", {"microservices", "distributed systems", "kafka", "redis", "aws sqs"}),
    "databases": ("SQL & databases", {"sql", "postgresql", "mysql", "mongodb", "elasticsearch"}),
    "cloud_devops": ("Cloud & DevOps", {"aws", "aws s3", "aws ecs", "gcp", "azure", "docker", "kubernetes", "terraform", "ci/cd"}),
    "python": ("Python", {"python", "fastapi", "django"}),
    "dsa": ("Coding & algorithms", {"dsa"}),
    "system_design": ("System design", {"system design"}),
    "llm_fundamentals": ("LLMs & transformers", {"llms", "generative ai", "transformers", "llm apis", "nlp"}),
    "prompting": ("Prompt engineering & tool calling", {"prompt engineering", "tool calling"}),
    "rag": ("RAG, embeddings & vector DBs", {"rag", "embeddings", "vector databases", "llamaindex"}),
    "agents": ("AI agents & orchestration", {"ai agents", "langchain", "langgraph"}),
    "llm_eval": ("LLM evaluation & reliability", {"llm evaluation"}),
    "ml_fundamentals": ("ML & deep learning", {"machine learning", "deep learning", "pytorch", "tensorflow", "fine-tuning", "mlops", "multimodal"}),
    "behavioral": ("Behavioral & leadership (STAR)", set()),
}
TOPIC_LABELS = {k: v[0] for k, v in TOPICS.items()}
_SKILL_TOPIC = {skill: topic for topic, (_, skills) in TOPICS.items() for skill in skills}

HALF_LIFE_DAYS = 30
SELF_RATING_WEIGHT = 0.5  # one self-rating counts as half a fresh coach answer
TARGET = 75  # proficiency where a topic stops counting as a gap
HOURS_PER_POINT = 0.8 / 100  # prep hours per (weight % x points below target): a full gap on everything ≈ 36 h
# Interviews rarely go deep on tooling, however many tools a JD lists.
_TOPIC_CAP = {"cloud_devops": 1.5, "databases": 2.0}


def topic_weights(job: Job) -> dict[str, int]:
    """Percent weight per topic for this job's interviews (sums to 100)."""
    raw: dict[str, float] = {"dsa": 2, "system_design": 2, "behavioral": 1.5}
    if job.seniority in ("senior", "staff", "principal", "lead"):
        raw["system_design"] += 1
    for skill in job.skills or []:
        topic = _SKILL_TOPIC.get(skill)
        if topic:
            raw[topic] = min(_TOPIC_CAP.get(topic, 3.0), raw.get(topic, 0) + 1)
    if job.role_family in ("ai_engineer", "ai_backend"):
        raw.setdefault("llm_fundamentals", 1)
    total = sum(raw.values())
    weights = {t: round(100 * w / total) for t, w in raw.items()}
    # Fix rounding so the weights add up to exactly 100.
    top = max(weights, key=weights.get)
    weights[top] += 100 - sum(weights.values())
    return dict(sorted(weights.items(), key=lambda kv: -kv[1]))


@dataclass
class Proficiency:
    score: int | None
    evidence: int  # number of scored coach answers
    self_rating: int | None
    last_at: datetime | None


def proficiencies(session: Session, now: datetime | None = None) -> dict[str, Proficiency]:
    now = now or datetime.now(timezone.utc)
    sums: dict[str, list[float]] = {t: [0.0, 0.0] for t in TOPICS}
    counts = dict.fromkeys(TOPICS, 0)
    last: dict[str, datetime | None] = dict.fromkeys(TOPICS)
    for ev in session.scalars(select(ProficiencyEvent)):
        if ev.topic not in TOPICS:
            continue
        age_days = max(0.0, (now - ev.at).total_seconds() / 86400)
        w = 0.5 ** (age_days / HALF_LIFE_DAYS)
        sums[ev.topic][0] += w * ev.score
        sums[ev.topic][1] += w
        counts[ev.topic] += 1
        if last[ev.topic] is None or ev.at > last[ev.topic]:
            last[ev.topic] = ev.at
    ratings = {r.topic: r.rating for r in session.scalars(select(TopicSelfRating))}

    out = {}
    for t in TOPICS:
        total, weight = sums[t]
        if t in ratings:
            total += SELF_RATING_WEIGHT * ratings[t] * 20
            weight += SELF_RATING_WEIGHT
        out[t] = Proficiency(round(total / weight) if weight else None, counts[t], ratings.get(t), last[t])
    return out


def readiness(job: Job, profs: dict[str, Proficiency], floor: int) -> tuple[int | None, dict[str, Any]]:
    weights = topic_weights(job)
    topics = []
    known_weight = 0
    total = 0.0
    for t, w in weights.items():
        p = profs[t].score
        if p is not None:
            known_weight += w
        score = p if p is not None else floor
        total += w * score
        gap_hours = 0 if score >= TARGET else math.ceil((TARGET - score) * w * HOURS_PER_POINT)
        topics.append({"topic": t, "label": TOPIC_LABELS[t], "weight": w, "score": score, "known": p is not None,
                       "evidence": profs[t].evidence, "gap_hours": gap_hours})
    gaps = sorted((x for x in topics if x["score"] < TARGET), key=lambda x: -x["weight"] * (TARGET - x["score"]))
    breakdown = {
        "topics": topics,
        "coverage": known_weight,  # % of topic weight backed by a self-rating or coach score
        "top_gaps": [g["topic"] for g in gaps[:3]],
        "prep_hours_est": sum(x["gap_hours"] for x in topics),
    }
    if known_weight == 0:
        return None, breakdown
    return round(total / 100), breakdown


def refresh_readiness(session: Session) -> int:
    """Recompute readiness for every scored open job. Rules only, so it's cheap."""
    profs = proficiencies(session)
    floor = prefs.get_section(session, "scoring").missing_data_floor
    rows = session.execute(select(Job, JobScore).join(JobScore, JobScore.job_id == Job.id).where(Job.status == "open")).all()
    for job, score in rows:
        score.readiness, score.readiness_breakdown = readiness(job, profs, floor)
    session.flush()
    return len(rows)


def job_readiness(session: Session, job: Job) -> tuple[int | None, dict[str, Any]]:
    floor = prefs.get_section(session, "scoring").missing_data_floor
    return readiness(job, proficiencies(session), floor)
