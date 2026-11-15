import json
import subprocess

import pytest

from app.llm.engines import ClaudeCodeEngine, LLMError, parse_cli_output


def cli_payload(**overrides):
    payload = {
        "type": "result", "is_error": False, "result": "done", "total_cost_usd": 0.0012,
        "duration_ms": 900, "usage": {"input_tokens": 120, "output_tokens": 8, "cache_read_input_tokens": 50},
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_parses_structured_output_and_usage():
    out = parse_cli_output(cli_payload(structured_output={"role_family": "ai_engineer"}), "", "haiku", True)
    assert out.data == {"role_family": "ai_engineer"}
    assert (out.input_tokens, out.output_tokens, out.cache_read_tokens) == (120, 8, 50)
    assert out.cost_usd_equiv == pytest.approx(0.0012)


def test_falls_back_to_json_in_fenced_result_text():
    out = parse_cli_output(cli_payload(result='```json\n{"a": 1}\n```'), "", "haiku", True)
    assert out.data == {"a": 1}


def test_not_logged_in_gives_actionable_error():
    with pytest.raises(LLMError, match="/login"):
        parse_cli_output(cli_payload(is_error=True, result="Not logged in · Please run /login"), "", "haiku", False)


def test_non_json_output_raises():
    with pytest.raises(LLMError, match="non-JSON"):
        parse_cli_output("boom", "stack trace", "haiku", False)


def test_unparseable_model_json_raises():
    with pytest.raises(LLMError, match="expected JSON"):
        parse_cli_output(cli_payload(result="not json"), "", "haiku", True)


def test_command_disables_tools_and_settings():
    cmd = ClaudeCodeEngine("claude").build_command("haiku", "sys", {"type": "object"})
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in cmd and "--no-session-persistence" in cmd
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == {"type": "object"}


def test_run_strips_api_keys_and_sends_prompt_on_stdin(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout=cli_payload(), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ClaudeCodeEngine().run(model="haiku", system="s", prompt="hello", schema=None, timeout_s=5)
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert seen["input"] == "hello"


def test_missing_binary_raises(monkeypatch):
    engine = ClaudeCodeEngine("definitely-not-a-real-claude-binary")
    with pytest.raises(LLMError, match="not found"):
        engine.run(model="haiku", system="s", prompt="p", schema=None, timeout_s=5)
