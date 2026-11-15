"""Facts store: the only source agents may use to describe you.

`data/profile_facts.yaml` is the source of truth; `sync_from_file` mirrors it
into Postgres (adds, updates, and removes facts deleted from the file).
Facts marked `needs_confirmation` are stored but never handed to agents.
"""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.models import FACT_KINDS, Employment, ProfileFact, Setting


class EmploymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    company: str
    title_on_resume: str | None = None
    official_title: str | None = None
    location: str | None = None
    start: str = Field(pattern=r"^\d{4}-\d{2}$")
    end: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")


class FactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal[FACT_KINDS]  # type: ignore[valid-type]
    employer: str | None = None
    text: str
    skills: list[str] = []
    metric: str | None = None
    needs_confirmation: bool = False
    correction: str | None = None
    status: str | None = None

    @model_validator(mode="after")
    def employer_only_for_professional(self) -> "FactIn":
        if self.kind == "professional" and not self.employer:
            raise ValueError(f"{self.id}: professional facts need an employer")
        if self.kind != "professional" and self.employer:
            raise ValueError(f"{self.id}: only professional facts can name an employer")
        return self


class FactsFile(BaseModel):
    person: dict[str, Any] = {}
    employment: list[EmploymentIn]
    facts: list[FactIn]
    education: list[str] = []
    publications: list[str] = []
    awards: list[str] = []

    @model_validator(mode="after")
    def references_valid(self) -> "FactsFile":
        employers = {e.id for e in self.employment}
        ids = [f.id for f in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate fact ids")
        for f in self.facts:
            if f.employer and f.employer not in employers:
                raise ValueError(f"{f.id}: unknown employer {f.employer!r}")
        return self


def load_file(path: Path) -> FactsFile:
    if not path.exists():
        raise FileNotFoundError(f"facts file not found: {path}")
    return FactsFile.model_validate(yaml.safe_load(path.read_text()))


def sync_from_file(session: Session, path: Path) -> dict[str, int]:
    parsed = load_file(path)

    for e in parsed.employment:
        session.merge(Employment(**e.model_dump()))

    for f in parsed.facts:
        session.merge(ProfileFact(
            id=f.id, kind=f.kind, employer_id=f.employer, text=f.text, skills=f.skills,
            metric=f.metric, needs_confirmation=f.needs_confirmation,
            note=f.correction or f.status, source_doc=path.name,
        ))
    session.flush()
    removed = session.execute(
        delete(ProfileFact).where(ProfileFact.id.not_in([f.id for f in parsed.facts]))
    ).rowcount

    extras = {k: getattr(parsed, k) for k in ("person", "education", "publications", "awards")}
    session.merge(Setting(key="profile", value=extras))

    summary = {
        "facts": len(parsed.facts),
        "needs_confirmation": sum(f.needs_confirmation for f in parsed.facts),
        "removed": removed,
    }
    audit.record(session, "user", "facts.sync", path.name, **summary)
    return summary


def usable_facts(session: Session) -> list[ProfileFact]:
    """Facts agents may use. Unconfirmed facts are excluded on purpose."""
    return list(session.scalars(
        select(ProfileFact).where(ProfileFact.needs_confirmation.is_(False)).order_by(ProfileFact.id)
    ))
