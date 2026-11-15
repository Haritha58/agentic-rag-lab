"""Public job boards: remote boards, the Himalayas search and Arbeitnow (visa-sponsorship filter)."""

from app.discovery.classify import LocationHints, role_family
from app.discovery.salary import from_struct
from app.discovery.sources.base import Feed, Http, RawJob, parse_dt
from app.discovery.text import html_to_text

HIMALAYAS_QUERIES = (
    "ai engineer", "llm engineer", "generative ai engineer", "machine learning engineer",
    "backend engineer", "java developer", "senior software engineer", "platform engineer",
)


def _wanted(title: str) -> bool:
    return role_family(title, "") is not None


def remotive(http: Http) -> list[RawJob]:
    data = http.get_json("https://remotive.com/api/remote-jobs", {"category": "software-dev"})
    out = []
    for j in data.get("jobs", []):
        if not _wanted(j["title"]):
            continue
        out.append(RawJob(
            source="remotive", source_job_id=str(j["id"]), company_name=j["company_name"], title=j["title"],
            url=j["url"], apply_url=j["url"], location=j.get("candidate_required_location") or "",
            description=html_to_text(j.get("description")), posted_at=parse_dt(j.get("publication_date")),
            hints=LocationHints(remote=True),
        ))
    return out


def remoteok(http: Http) -> list[RawJob]:
    """Remote OK's API terms require crediting them with a link; the dashboard shows 'via Remote OK'."""
    data = http.get_json("https://remoteok.com/api")
    out = []
    for j in data[1:]:  # first element is the legal notice
        if not _wanted(j.get("position", "")):
            continue
        out.append(RawJob(
            source="remoteok", source_job_id=str(j["id"]), company_name=j.get("company", ""), title=j["position"],
            url=j["url"], apply_url=j.get("apply_url"), location=j.get("location") or "",
            description=html_to_text(j.get("description")), posted_at=parse_dt(j.get("date")),
            hints=LocationHints(remote=True),
            salary=from_struct("USD", j.get("salary_min") or None, j.get("salary_max") or None, "year"),
        ))
    return out


def arbeitnow(http: Http) -> list[RawJob]:
    out = []
    for page in (1, 2, 3):
        data = http.get_json("https://www.arbeitnow.com/api/job-board-api", {"visa_sponsorship": "true", "page": page})
        for j in data.get("data", []):
            if not _wanted(j["title"]):
                continue
            out.append(RawJob(
                source="arbeitnow", source_job_id=j["slug"], company_name=j["company_name"], title=j["title"],
                url=j["url"], apply_url=j["url"], location=j.get("location") or "",
                description=html_to_text(j.get("description")), posted_at=parse_dt(j.get("created_at")),
                hints=LocationHints(remote=True if j.get("remote") else None, visa_sponsorship=True),
            ))
        if not (data.get("links") or {}).get("next"):
            break
    return out


def himalayas(query: str, india: bool):
    def fetch(http: Http) -> list[RawJob]:
        params = {"q": query, **({"country": "India"} if india else {"worldwide": "true"})}
        out = []
        for page in (1, 2):
            data = http.get_json("https://himalayas.app/jobs/api/search", {**params, "page": page})
            jobs = data.get("jobs", [])
            for j in jobs:
                if not _wanted(j["title"]):
                    continue
                restrictions = j.get("locationRestrictions") or []
                out.append(RawJob(
                    source="himalayas", source_job_id=j["guid"], company_name=j.get("companyName", ""),
                    title=j["title"], url=j["guid"], apply_url=j.get("applicationLink"),
                    location=", ".join(restrictions) or "Worldwide",
                    description=html_to_text(j.get("description")) or j.get("excerpt", ""),
                    posted_at=parse_dt(j.get("pubDate")), expires_at=parse_dt(j.get("expiryDate")),
                    hints=LocationHints(remote=True, location_restrictions=restrictions,
                                        country_codes=["IN"] if "India" in restrictions else []),
                    salary=from_struct(j.get("currency"), j.get("minSalary"), j.get("maxSalary"), j.get("salaryPeriod")),
                ))
            if len(jobs) < 20:
                break
        return out
    return fetch


def board_feeds() -> list[Feed]:
    feeds = [
        Feed("remotive", remotive),
        Feed("remoteok", remoteok),
        Feed("arbeitnow", arbeitnow, complete=False),
    ]
    for q in HIMALAYAS_QUERIES:
        feeds.append(Feed(f"himalayas:india:{q}", himalayas(q, india=True), complete=False))
        feeds.append(Feed(f"himalayas:worldwide:{q}", himalayas(q, india=False), complete=False))
    return feeds
