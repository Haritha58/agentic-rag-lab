from sqlalchemy import select

from app.discovery.sources import Feed
from app.models import Company, Job
from tests.test_pipeline import profile, raw, run  # noqa: F401 (profile is a fixture)


def seed(session):
    run(session, [Feed("greenhouse:acme", lambda http: [
        raw(1),
        raw(2, title="Senior Java Developer", location="Remote - India", description="Java Spring Boot. 20 - 24 LPA"),
        raw(3, title="Backend Engineer", location="Remote - Worldwide", description="Go services.", company_name="Globex"),
        raw(4, title="Backend Engineer", location="Pune, India", description="Python. Salary 10 - 12 LPA"),
    ])])


def test_list_filters_and_segment_counts(client, session):
    seed(session)
    body = client.get("/api/jobs").json()
    titles = {j["title"] for j in body["jobs"]}
    assert "Backend Engineer" in titles  # worldwide job
    assert body["segment_counts"] == {"IN_ONSITE_HYBRID": 1, "IN_REMOTE": 1, "INTL_REMOTE": 1}  # Pune job is below the pay floor
    in_remote = client.get("/api/jobs", params={"segment": "IN_REMOTE"}).json()["jobs"]
    assert [j["title"] for j in in_remote] == ["Senior Java Developer"]
    assert client.get("/api/jobs", params={"min_salary_lpa": 30}).json()["jobs"][0]["title"] == "Senior AI Engineer"


def test_pay_floor_hides_only_posted_low_pay(client, session):
    seed(session)
    titles = [j["title"] for j in client.get("/api/jobs", params={"segment": "IN_ONSITE_HYBRID"}).json()["jobs"]]
    assert titles == ["Senior AI Engineer"]  # the 10-12 LPA Pune job is below your 20 LPA floor
    shown = client.get("/api/jobs", params={"segment": "IN_ONSITE_HYBRID", "hide_below_floor": False}).json()["jobs"]
    assert len(shown) == 2


def test_detail_shortlist_and_overview(client, session):
    seed(session)
    job_id = session.scalar(select(Job.id).where(Job.title == "Senior AI Engineer"))
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["suitability_breakdown"]["technical"]["weight"] == 35
    assert detail["readiness"] is None and "evidence" in detail
    assert client.patch(f"/api/jobs/{job_id}", json={"user_status": "shortlisted"}).json()["user_status"] == "shortlisted"
    assert client.get("/api/overview").json()["shortlisted"] == 1
    assert job_id not in [j["id"] for j in client.get("/api/jobs").json()["jobs"]]  # default view = new only
    assert client.patch(f"/api/jobs/{job_id}", json={"user_status": "bogus"}).status_code == 422
    assert client.get("/api/jobs/999999").status_code == 404


def test_company_category_override(client, session):
    seed(session)
    acme = session.scalar(select(Company).where(Company.key == "acme ai"))
    out = client.patch(f"/api/companies/{acme.id}", json={"category": 1}).json()
    assert out["category"] == 1
    assert session.get(Company, acme.id).category_source == "user"
    names = [c["name"] for c in client.get("/api/companies").json()]
    assert "Acme AI" in names and "Globex" in names


def test_top_picks_endpoint(client, session, profile):
    seed(session)
    picks = client.get("/api/jobs/top-picks", params={"n": 3}).json()
    assert picks and all("pick_reason" in p for p in picks)


def test_fresh_sort_favours_recent_postings(client, session):
    from datetime import datetime, timedelta, timezone

    from app.models import JobScore

    seed(session)
    jobs = {j.title + j.location_raw: j for j in session.scalars(select(Job))}
    old = jobs["Senior Java DeveloperRemote - India"]
    new = jobs["Backend EngineerRemote - Worldwide"]
    old.posted_at = datetime.now(timezone.utc) - timedelta(days=20)
    new.posted_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.get(JobScore, old.id).opportunity = 80  # better fit, but 20 days old: 80 * 0.6 = 48
    session.get(JobScore, new.id).opportunity = 60  # fresh: 60 * 1.0 = 60
    session.flush()
    ids = lambda sort: [j["id"] for j in client.get("/api/jobs", params={"sort": sort, "hide_below_floor": False}).json()["jobs"]]
    fresh = ids("fresh")
    assert fresh.index(new.id) < fresh.index(old.id)
    opp = ids("opportunity")
    assert opp.index(old.id) < opp.index(new.id)
    assert ids("oldest")[0] == old.id



def test_old_postings_hidden_unless_tracked(client, session):
    from datetime import datetime, timedelta, timezone

    seed(session)
    jobs = list(session.scalars(select(Job)))
    stale, shortlisted, applied = jobs[0], jobs[1], jobs[2]
    for j in (stale, shortlisted, applied):
        j.posted_at = datetime.now(timezone.utc) - timedelta(days=400)
    shortlisted.user_status = "shortlisted"
    session.flush()
    client.post("/api/applications", json={"job_id": applied.id})
    shown = {j["id"] for j in client.get("/api/jobs", params={"user_status": "all", "hide_below_floor": False}).json()["jobs"]}
    assert stale.id not in shown and shortlisted.id in shown and applied.id in shown
    assert client.get("/api/overview").json()["max_posting_age_days"] == 30

    stale.posted_at = datetime.now(timezone.utc) - timedelta(days=200)
    assert client.put("/api/settings/discovery", json={"max_posting_age_days": 365}).status_code == 200
    shown = {j["id"] for j in client.get("/api/jobs", params={"user_status": "all", "hide_below_floor": False}).json()["jobs"]}
    assert stale.id in shown  # the limit is a setting you can change
