from datetime import date, timedelta

from sqlalchemy import select

from app.models import StatusEvent
from tests.test_coach import job_id  # noqa: F401 (fixture)
from tests.test_pipeline import profile  # noqa: F401 (fixture)


def manual(client, **extra):
    r = client.post("/api/applications", json={"company": "Acme AI", "title": "AI Engineer", "channel": "referral", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_log_application_from_a_job(client, job_id):
    r = client.post("/api/applications", json={"job_id": job_id, "resume_version": "Resume_v5.pdf"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["job_id"] == job_id and a["company"] and a["title"] and a["url"]
    assert a["status"] == "applied" and a["applied_at"] == date.today().isoformat()
    assert a["follow_up_on"] == (date.today() + timedelta(days=7)).isoformat()
    assert [e["to_status"] for e in a["events"]] == ["applied"]

    dup = client.post("/api/applications", json={"job_id": job_id})
    assert dup.status_code == 409
    assert [x["id"] for x in client.get(f"/api/applications?job_id={job_id}").json()] == [a["id"]]


def test_manual_application_needs_company_and_role(client):
    assert client.post("/api/applications", json={"company": "Acme"}).status_code == 422
    assert client.post("/api/applications", json={"job_id": 999999}).status_code == 404
    assert manual(client)["channel"] == "referral"


def test_many_rounds_and_status_history(client, session):
    a = manual(client)
    r1 = client.post(f"/api/applications/{a['id']}/rounds", json={"round_type": "hr_screen", "scheduled_at": "2030-01-10T10:30"})
    assert r1.status_code == 201, r1.text
    after = r1.json()
    assert after["status"] == "interviewing"
    assert after["rounds"][0]["round_no"] == 1 and after["rounds"][0]["coach_round"] == "behavioral"
    assert after["rounds"][0]["scheduled_at"].endswith("+05:30")  # read as IST
    assert after["next_round"]["round_no"] == 1

    for t in ("coding", "system_design", "technical_ai", "managerial"):
        out = client.post(f"/api/applications/{a['id']}/rounds", json={"round_type": t}).json()
    assert [r["round_no"] for r in out["rounds"]] == [1, 2, 3, 4, 5]
    assert client.post(f"/api/applications/{a['id']}/rounds", json={"round_type": "coding", "round_no": 3}).status_code == 409

    rid = out["rounds"][0]["id"]
    upd = client.patch(f"/api/rounds/{rid}", json={"status": "cleared", "questions": "Why leave?", "self_rating": 4}).json()
    assert upd["rounds_cleared"] == 1 and upd["rounds"][0]["questions"] == "Why leave?"
    assert client.patch(f"/api/rounds/{rid}", json={"self_rating": 9}).status_code == 422

    done = client.patch(f"/api/applications/{a['id']}", json={"status": "offer", "status_note": "Offer letter by email"}).json()
    assert [e["to_status"] for e in done["events"]] == ["applied", "interviewing", "offer"]
    assert done["events"][-1]["note"] == "Offer letter by email"
    assert session.scalar(select(StatusEvent.evidence_type).order_by(StatusEvent.id.desc())) == "user_action"

    gone = client.delete(f"/api/rounds/{out['rounds'][4]['id']}").json()
    assert gone["rounds_total"] == 4


def test_follow_up_due_only_while_waiting(client):
    a = manual(client, applied_at=(date.today() - timedelta(days=10)).isoformat())
    assert client.get(f"/api/applications/{a['id']}").json()["follow_up_due"] is True
    client.patch(f"/api/applications/{a['id']}", json={"status": "rejected"})
    assert client.get(f"/api/applications/{a['id']}").json()["follow_up_due"] is False


def test_bad_status_and_delete(client):
    a = manual(client)
    assert client.patch(f"/api/applications/{a['id']}", json={"status": "hired"}).status_code == 422
    assert client.delete(f"/api/applications/{a['id']}").status_code == 204
    assert client.get(f"/api/applications/{a['id']}").status_code == 404


def test_meta(client):
    m = client.get("/api/applications/meta").json()
    assert "interviewing" in m["statuses"] and "hr_screen" in m["round_types"]
    assert all(v["coach_round"] for v in m["round_types"].values())


def email(**extra):
    return {"gmail_msg_id": "m1", "thread_id": "t1", "category": "application_confirmation",
            "sender": "noreply-recruiting@acme.com", "subject": "Thanks for applying", "summary": "Confirmation",
            "received_at": "2026-11-14T03:17:08Z", **extra}


def test_email_creates_application_with_email_evidence(client):
    r = client.post("/api/emails", json=email(new_application={"company": "Acme", "title": "AI Engineer"}))
    assert r.status_code == 201, r.text
    app_id = r.json()["application_id"]
    a = client.get(f"/api/applications/{app_id}").json()
    assert a["applied_at"] == "2026-11-14" and a["emails"][0]["gmail_msg_id"] == "m1"
    assert a["events"][0]["evidence_type"] == "email" and a["events"][0]["evidence_ref"] == "m1"

    again = client.post("/api/emails", json=email(new_application={"company": "Acme", "title": "AI Engineer"}))
    assert again.status_code == 200 and again.json()["duplicate"] is True
    assert len(client.get("/api/applications").json()) == 1
    assert client.get("/api/emails/seen?ids=m1,zz").json() == ["m1"]


def test_reply_in_same_thread_moves_status_with_evidence(client):
    app_id = client.post("/api/emails", json=email(new_application={"company": "Acme", "title": "AI Engineer"})).json()["application_id"]
    r = client.post("/api/emails", json=email(gmail_msg_id="m2", category="interview_invite", needs_reply=True,
                                              summary="Wants a call Tuesday", set_status="screening"))
    assert r.json()["application_id"] == app_id
    a = client.get(f"/api/applications/{app_id}").json()
    assert a["status"] == "screening" and a["events"][-1]["evidence_ref"] == "m2"
    pending = client.get("/api/emails?pending=true").json()
    assert [e["gmail_msg_id"] for e in pending] == ["m2"] and pending[0]["application"]["company"] == "Acme"
    client.patch(f"/api/emails/{pending[0]['id']}", json={"handled": True})
    assert client.get("/api/emails?pending=true").json() == []


def test_unlinked_email_is_kept(client):
    r = client.post("/api/emails", json=email(gmail_msg_id="m9", thread_id="t9", category="recruiter_reply", needs_reply=True))
    assert r.status_code == 201 and r.json()["application_id"] is None
    assert client.post("/api/emails", json=email(gmail_msg_id="m10", category="spam")).status_code == 422


def test_email_links_to_existing_job_application(client, job_id):
    mine = client.post("/api/applications", json={"job_id": job_id}).json()
    r = client.post("/api/emails", json=email(new_application={"job_id": job_id, "company": "X", "title": "Y"}))
    assert r.json()["application_id"] == mine["id"]
    fresh = client.post("/api/emails", json=email(gmail_msg_id="m7", thread_id="t7", new_application={"job_id": 999999, "company": "X", "title": "Y"}))
    assert fresh.status_code == 404


def test_main_resume_listed_first(client):
    client.put("/api/settings/documents", json={"main_resume_path": "/tmp/My_Resume.pdf"})
    m = client.get("/api/applications/meta").json()
    assert m["main_resume"] == "My_Resume.pdf" and m["resume_versions"][0] == "My_Resume.pdf"
