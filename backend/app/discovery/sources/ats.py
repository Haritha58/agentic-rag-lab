"""Company career boards via the public job-board APIs that ATS vendors publish for embedding."""

from app.discovery.classify import LocationHints, role_family
from app.discovery.salary import from_struct
from app.discovery.sources.base import Http, RawJob, parse_dt
from app.discovery.text import html_to_text


def _title_may_match(title: str) -> bool:
    # Cheap pre-check (no description yet) so big boards don't need full processing per job.
    return role_family(title, "") is not None


def greenhouse(company: str, slug: str):
    def fetch(http: Http) -> list[RawJob]:
        data = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", {"content": "true"})
        out = []
        for j in data.get("jobs", []):
            if not _title_may_match(j["title"]):
                continue
            location = (j.get("location") or {}).get("name", "")
            out.append(RawJob(
                source="greenhouse", source_job_id=str(j["id"]), company_name=company, title=j["title"],
                url=j["absolute_url"], apply_url=j["absolute_url"], location=location,
                description=html_to_text(j.get("content")),
                posted_at=parse_dt(j.get("first_published") or j.get("updated_at")),
                company_ats="greenhouse", company_slug=slug,
            ))
        return out
    return fetch


def lever(company: str, slug: str):
    def fetch(http: Http) -> list[RawJob]:
        data = http.get_json(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})
        out = []
        for j in data:
            if not _title_may_match(j["text"]):
                continue
            cats = j.get("categories") or {}
            parts = [j.get("descriptionPlain") or ""]
            for lst in j.get("lists") or []:
                parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
            parts.append(j.get("additionalPlain") or "")
            workplace = (j.get("workplaceType") or "").lower()
            sal = j.get("salaryRange") or {}
            out.append(RawJob(
                source="lever", source_job_id=j["id"], company_name=company, title=j["text"],
                url=j["hostedUrl"], apply_url=j.get("applyUrl"),
                location=", ".join(cats.get("allLocations") or [cats.get("location") or ""]),
                description="\n\n".join(p for p in parts if p),
                posted_at=parse_dt(j.get("createdAt")),
                hints=LocationHints(
                    remote=True if workplace == "remote" else (False if workplace == "onsite" else None),
                    hybrid=workplace == "hybrid" or None,
                    country_codes=[j["country"]] if j.get("country") else [],
                ),
                salary=from_struct(sal.get("currency"), sal.get("min"), sal.get("max"), sal.get("interval")),
                company_ats="lever", company_slug=slug,
            ))
        return out
    return fetch


def ashby(company: str, slug: str):
    def fetch(http: Http) -> list[RawJob]:
        data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", {"includeCompensation": "true"})
        out = []
        for j in data.get("jobs", []):
            if not j.get("isListed", True) or not _title_may_match(j["title"]):
                continue
            locations = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or ""
            workplace = (j.get("workplaceType") or "").lower()
            salary = None
            for comp in (j.get("compensation") or {}).get("summaryComponents") or []:
                if comp.get("compensationType") == "Salary":
                    salary = from_struct(comp.get("currencyCode"), comp.get("minValue"), comp.get("maxValue"), comp.get("interval"))
                    break
            out.append(RawJob(
                source="ashby", source_job_id=j["id"], company_name=company, title=j["title"],
                url=j["jobUrl"], apply_url=j.get("applyUrl"),
                location=", ".join(x for x in locations + [country] if x),
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                posted_at=parse_dt(j.get("publishedAt")),
                hints=LocationHints(
                    remote=True if (j.get("isRemote") or workplace == "remote") else (False if workplace == "onsite" else None),
                    hybrid=workplace == "hybrid" or None,
                    country_codes=["IN"] if country.lower() == "india" else [],
                ),
                salary=salary, company_ats="ashby", company_slug=slug,
            ))
        return out
    return fetch


def smartrecruiters(company: str, slug: str):
    def fetch(http: Http) -> list[RawJob]:
        base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        listing, offset = [], 0
        while True:
            page = http.get_json(base, {"limit": 100, "offset": offset})
            listing += page.get("content", [])
            offset += 100
            if offset >= page.get("totalFound", 0) or offset >= 1000:
                break
        out = []
        for j in listing:
            if not _title_may_match(j["name"]):
                continue
            detail = http.get_json(f"{base}/{j['id']}")  # list view has no description
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            desc = "\n\n".join(html_to_text(s.get("text")) for s in sections.values() if s.get("text"))
            loc = j.get("location") or {}
            out.append(RawJob(
                source="smartrecruiters", source_job_id=str(j["id"]), company_name=company, title=j["name"],
                url=detail.get("postingUrl") or f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                apply_url=detail.get("applyUrl"), location=loc.get("fullLocation", ""), description=desc,
                posted_at=parse_dt(j.get("releasedDate")),
                hints=LocationHints(
                    remote=bool(loc.get("remote")) or None, hybrid=bool(loc.get("hybrid")) or None,
                    country_codes=[loc["country"].upper()] if loc.get("country") else [],
                ),
                company_ats="smartrecruiters", company_slug=slug,
            ))
        return out
    return fetch


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters}
