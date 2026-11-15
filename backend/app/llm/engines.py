"""LLM engines. Agents never call these directly; they go through Gateway.

ClaudeCodeEngine runs `claude -p` on this Mac, so calls use your Claude Pro
login instead of a paid API key. It runs with no tools, no MCP servers and no
project settings, in an empty temp directory: the model only sees the prompt.
That matters because prompts contain untrusted text (job descriptions, emails).
"""

import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

# Removed from the child env so `claude` can't silently bill an API key.
_API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    data: Any = None  # parsed JSON when a schema was requested
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd_equiv: float = 0.0
    duration_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class Engine(Protocol):
    name: str

    def run(
        self, *, model: str, system: str, prompt: str, schema: dict[str, Any] | None, timeout_s: int
    ) -> LLMResult: ...


class ClaudeCodeEngine:
    name = "claude_code"

    def __init__(self, claude_bin: str = "claude"):
        self.claude_bin = claude_bin

    def build_command(self, model: str, system: str, schema: dict[str, Any] | None) -> list[str]:
        cmd = [
            self.claude_bin, "-p",
            "--output-format", "json",
            "--model", model,
            "--tools", "",
            "--no-session-persistence",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--system-prompt", system,
        ]
        if schema is not None:
            cmd += ["--json-schema", json.dumps(schema)]
        return cmd

    def run(self, *, model, system, prompt, schema, timeout_s):
        env = {k: v for k, v in os.environ.items() if k not in _API_KEY_VARS}
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="jobpilot-llm-") as workdir:
            try:
                proc = subprocess.run(
                    self.build_command(model, system, schema),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    cwd=workdir,
                    env=env,
                )
            except FileNotFoundError as e:
                raise LLMError(f"`{self.claude_bin}` not found. Install Claude Code or set CLAUDE_BIN.") from e
            except subprocess.TimeoutExpired as e:
                raise LLMError(f"claude timed out after {timeout_s}s") from e
        result = parse_cli_output(proc.stdout, proc.stderr, model, schema is not None)
        result.duration_ms = result.duration_ms or int((time.monotonic() - started) * 1000)
        return result


def parse_cli_output(stdout: str, stderr: str, model: str, expect_json: bool) -> LLMResult:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as e:
        detail = (stderr or stdout).strip()[:500]
        raise LLMError(f"claude returned non-JSON output: {detail}") from e

    text = payload.get("result") or ""
    if payload.get("is_error"):
        if "not logged in" in text.lower():
            raise LLMError("Claude Code is not logged in. Run `claude` in a terminal and use /login.")
        raise LLMError(f"claude error: {text or payload.get('terminal_reason')}")

    data = None
    if expect_json:
        data = payload.get("structured_output")
        if data is None:
            data = _json_from_text(text)

    usage = payload.get("usage") or {}
    return LLMResult(
        text=text,
        model=model,
        data=data,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cost_usd_equiv=float(payload.get("total_cost_usd") or 0),
        duration_ms=payload.get("duration_ms", 0),
        raw=payload,
    )


def _json_from_text(text: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise LLMError(f"expected JSON from model, got: {text[:300]}") from e


class FakeEngine:
    """Deterministic engine for tests and offline development."""

    name = "fake"

    def __init__(self, responses: list[Any] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def run(self, *, model, system, prompt, schema, timeout_s):
        self.calls.append({"model": model, "system": system, "prompt": prompt, "schema": schema})
        reply = self.responses.pop(0) if self.responses else {"ok": True}
        if isinstance(reply, Exception):
            raise reply
        if schema is not None:
            return LLMResult(text=json.dumps(reply), model=model, data=reply, input_tokens=10, output_tokens=5)
        return LLMResult(text=str(reply), model=model, input_tokens=10, output_tokens=5)
