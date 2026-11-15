import yaml

from app import api
from app.config import Settings
from app.llm import FakeEngine, LLMError, gateway


def test_health(client):
    assert client.get("/api/health").json()["db"] == "ok"


def test_settings_validation(client):
    assert client.get("/api/settings").json()["compensation"]["notice_period_days"] == 30
    bad = client.put("/api/settings/opportunity_weights", json={"technical_match": 90})
    assert bad.status_code == 422
    assert client.put("/api/settings/nope", json={}).status_code == 404
    ok = client.put("/api/settings/scoring", json={"missing_data_floor": 0})
    assert ok.status_code == 200 and ok.json()["missing_data_floor"] == 0


def test_facts_sync_and_list(client, monkeypatch, tmp_path):
    (tmp_path / "profile_facts.yaml").write_text(yaml.safe_dump({
        "employment": [{"id": "acme", "company": "Acme", "start": "2020-04"}],
        "facts": [{"id": "f1", "kind": "professional", "employer": "acme", "text": "Built queues"}],
    }))
    monkeypatch.setattr(api, "get_settings", lambda: Settings(data_dir=tmp_path))
    assert client.post("/api/facts/sync").json()["facts"] == 1
    body = client.get("/api/facts").json()
    assert body["usable"] == 1 and body["facts"][0]["employer"] == "Acme"


def test_facts_sync_missing_file_is_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "get_settings", lambda: Settings(data_dir=tmp_path))
    assert client.post("/api/facts/sync").status_code == 404


def test_llm_ping_ok_and_usage(client, monkeypatch):
    monkeypatch.setattr(gateway, "default_engine", lambda: FakeEngine([{"role_family": "ai_engineer"}]))
    ping = client.post("/api/llm/ping").json()
    assert ping == {"ok": True, "model": "haiku", "reply": {"role_family": "ai_engineer"}, "error": None}
    usage = client.get("/api/llm/usage").json()
    assert usage["calls_today"] == 1 and usage["last_30_days"][0]["task"] == "llm.ping"


def test_llm_ping_reports_engine_error(client, monkeypatch):
    monkeypatch.setattr(gateway, "default_engine", lambda: FakeEngine([LLMError("Claude Code is not logged in")]))
    ping = client.post("/api/llm/ping").json()
    assert ping["ok"] is False and "not logged in" in ping["error"]
