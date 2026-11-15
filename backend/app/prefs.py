"""User-editable preferences, stored as JSON rows in the `settings` table.

Defaults live here; the DB only holds overrides. Every section is validated
with a Pydantic model so a bad edit from the dashboard is rejected, not stored.
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.models import Setting


class OpportunityWeights(BaseModel):
    technical_match: int = 25
    work_life_balance: int = 20
    compensation: int = 15
    company_stability: int = 10
    growth_ai_exposure: int = 15
    arrangement_location: int = 10
    interview_accessibility: int = 5

    @model_validator(mode="after")
    def sums_to_100(self) -> "OpportunityWeights":
        total = sum(self.model_dump().values())
        if total != 100:
            raise ValueError(f"weights must sum to 100, got {total}")
        return self


class CompanyAllocation(BaseModel):
    medium: int = 60
    large: int = 30
    highly_competitive: int = 10

    @model_validator(mode="after")
    def sums_to_100(self) -> "CompanyAllocation":
        total = self.medium + self.large + self.highly_competitive
        if total != 100:
            raise ValueError(f"allocation must sum to 100, got {total}")
        return self


class Scoring(BaseModel):
    # Score given to an unknown component: below neutral so missing data never helps.
    missing_data_floor: int = Field(30, ge=0, le=50)
    high_match_min: int = 80
    medium_match_min: int = 60


class Compensation(BaseModel):
    current_fixed_lpa: float = 15.0
    current_total_lpa: float = 16.0
    target_lpa: float = 22.0
    # Below this the compensation sub-score drops sharply (~20% hike over current).
    soft_floor_lpa: float = 18.0
    hide_below_lpa: float = 15.0
    notice_period_days: int = 30
    last_working_day: str = ""  # YYYY-MM-DD once you've resigned; empty while still employed


class Segments(BaseModel):
    in_onsite_hybrid: bool = True
    in_remote: bool = True
    intl_remote: bool = True
    intl_relocation: bool = True
    show_unverified: bool = False
    # Onsite/hybrid and city-restricted remote jobs in this city score highest. Empty = no home city.
    home_city: str = ""


class Discovery(BaseModel):
    # Postings older than this are skipped by discovery and hidden from lists. Jobs you applied to
    # or shortlisted stay visible whatever their age.
    max_posting_age_days: int = Field(30, ge=1, le=365)


class Documents(BaseModel):
    # Absolute path of the resume you send by default; set it in Settings.
    main_resume_path: str = ""


class Llm(BaseModel):
    # Model aliases understood by `claude -p --model`.
    small: str = "haiku"
    mid: str = "sonnet"
    strong: str = "opus"
    # Guards the Pro plan's usage limits; calls beyond this are refused for the day.
    daily_call_limit: int = Field(60, ge=1)


SECTIONS: dict[str, type[BaseModel]] = {
    "opportunity_weights": OpportunityWeights,
    "company_allocation": CompanyAllocation,
    "scoring": Scoring,
    "compensation": Compensation,
    "segments": Segments,
    "discovery": Discovery,
    "documents": Documents,
    "llm": Llm,
}


def get_section(session: Session, key: str) -> BaseModel:
    model = SECTIONS[key]
    row = session.get(Setting, key)
    return model.model_validate(row.value) if row else model()


def get_all(session: Session) -> dict[str, Any]:
    return {key: get_section(session, key).model_dump() for key in SECTIONS}


def put_section(session: Session, key: str, value: dict[str, Any]) -> BaseModel:
    validated = SECTIONS[key].model_validate(value)
    row = session.get(Setting, key)
    if row:
        row.value = validated.model_dump()
    else:
        session.add(Setting(key=key, value=validated.model_dump()))
    return validated
