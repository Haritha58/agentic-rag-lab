from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app import facts
from app.config import PROJECT_ROOT

BASE = {
    "employment": [{"id": "acme", "company": "Acme", "start": "2020-04"}],
    "facts": [
        {"id": "f1", "kind": "professional", "employer": "acme", "text": "Built queues", "skills": ["SQS"]},
        {"id": "f2", "kind": "professional", "employer": "acme", "text": "Built RAG", "needs_confirmation": True},
        {"id": "l1", "kind": "learning", "text": "Studying LangGraph"},
    ],
}


def write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "profile_facts.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_sync_stores_facts_and_excludes_unconfirmed_from_usable(session, tmp_path):
    summary = facts.sync_from_file(session, write(tmp_path, BASE))
    assert summary == {"facts": 3, "needs_confirmation": 1, "removed": 0}
    assert [f.id for f in facts.usable_facts(session)] == ["f1", "l1"]


def test_resync_removes_deleted_facts(session, tmp_path):
    facts.sync_from_file(session, write(tmp_path, BASE))
    smaller = {**BASE, "facts": BASE["facts"][:1]}
    assert facts.sync_from_file(session, write(tmp_path, smaller))["removed"] == 2


@pytest.mark.parametrize("bad_fact, message", [
    ({"id": "x", "kind": "learning", "employer": "acme", "text": "t"}, "only professional facts"),
    ({"id": "x", "kind": "professional", "text": "t"}, "need an employer"),
    ({"id": "x", "kind": "professional", "employer": "nowhere", "text": "t"}, "unknown employer"),
    ({"id": "f1", "kind": "learning", "text": "dup"}, "duplicate fact ids"),
])
def test_invalid_facts_rejected(tmp_path, bad_fact, message):
    data = {**BASE, "facts": [*BASE["facts"], bad_fact]}
    with pytest.raises(ValidationError, match=message):
        facts.load_file(write(tmp_path, data))


def test_real_facts_file_is_valid():
    path = PROJECT_ROOT / "data" / "profile_facts.yaml"
    if not path.exists():
        pytest.skip("no personal facts file on this machine")
    parsed = facts.load_file(path)
    assert any(f.kind == "professional" for f in parsed.facts)
