import pytest
from sqlalchemy import select

from app import prefs
from app.llm import FakeEngine, Gateway, LLMError, Tier
from app.models import LlmUsage


def test_routes_tier_to_model_and_records_usage(session):
    engine = FakeEngine([{"x": 1}])
    result = Gateway(session, engine).complete(task="t", system="s", prompt="p", tier=Tier.MID, schema={})
    assert result.data == {"x": 1}
    assert engine.calls[0]["model"] == "sonnet"
    row = session.scalars(select(LlmUsage)).one()
    assert (row.task, row.model, row.ok, row.input_tokens) == ("t", "sonnet", True, 10)


def test_engine_error_is_recorded_then_raised(session):
    gateway = Gateway(session, FakeEngine([LLMError("nope")]))
    with pytest.raises(LLMError):
        gateway.complete(task="t", system="s", prompt="p")
    row = session.scalars(select(LlmUsage)).one()
    assert row.ok is False and row.error == "nope"


def test_daily_limit_blocks_extra_calls(session):
    prefs.put_section(session, "llm", {"daily_call_limit": 2})
    gateway = Gateway(session, FakeEngine())
    gateway.complete(task="t", system="s", prompt="p")
    gateway.complete(task="t", system="s", prompt="p")
    with pytest.raises(LLMError, match="daily LLM call limit"):
        gateway.complete(task="t", system="s", prompt="p")
    assert gateway.calls_today() == 2
