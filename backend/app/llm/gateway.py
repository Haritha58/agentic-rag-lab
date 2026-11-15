"""Single entry point for every LLM call: model routing, daily limit, usage ledger."""

from datetime import datetime, time, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import prefs
from app.config import get_settings
from app.llm.engines import ClaudeCodeEngine, Engine, FakeEngine, LLMError, LLMResult
from app.models import LlmUsage

IST = ZoneInfo("Asia/Kolkata")


class Tier(str, Enum):
    SMALL = "small"    # extraction, triage, email classification
    MID = "mid"        # matching, resume tailoring, coach
    STRONG = "strong"  # rare: final reviews


def default_engine() -> Engine:
    settings = get_settings()
    if settings.llm_engine == "fake":
        return FakeEngine()
    if settings.llm_engine == "claude_code":
        return ClaudeCodeEngine(settings.claude_bin)
    raise ValueError(f"unknown LLM engine {settings.llm_engine!r}")


class Gateway:
    def __init__(self, session: Session, engine: Engine | None = None):
        self.session = session
        self.engine = engine or default_engine()

    def calls_today(self) -> int:
        start = datetime.combine(datetime.now(IST).date(), time.min, tzinfo=IST).astimezone(timezone.utc)
        return self.session.scalar(select(func.count()).select_from(LlmUsage).where(LlmUsage.at >= start)) or 0

    def complete(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        tier: Tier = Tier.SMALL,
        schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        llm_prefs = prefs.get_section(self.session, "llm")
        if self.calls_today() >= llm_prefs.daily_call_limit:
            raise LLMError(
                f"daily LLM call limit ({llm_prefs.daily_call_limit}) reached; raise it in Settings → LLM"
            )
        model = getattr(llm_prefs, tier.value)

        try:
            result = self.engine.run(
                model=model, system=system, prompt=prompt, schema=schema,
                timeout_s=get_settings().llm_timeout_s,
            )
        except LLMError as e:
            self._record(task, model, ok=False, error=str(e))
            raise
        self._record(task, model, ok=True, result=result)
        return result

    def _record(self, task: str, model: str, *, ok: bool, result: LLMResult | None = None, error: str | None = None):
        r = result or LLMResult(text="", model=model)
        self.session.add(LlmUsage(
            engine=self.engine.name, task=task, model=model,
            input_tokens=r.input_tokens, output_tokens=r.output_tokens,
            cache_read_tokens=r.cache_read_tokens, cost_usd_equiv=r.cost_usd_equiv,
            duration_ms=r.duration_ms, ok=ok, error=error,
        ))
        self.session.flush()
