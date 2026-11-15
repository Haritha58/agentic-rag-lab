"""Rule-based classification of a raw posting: role, seniority, location, segment.

Every decision that affects which tab a job lands in records the text it was
based on (`evidence`), so the dashboard can show *why*. When the rules can't
tell, the answer is "unknown"/UNVERIFIED, never the optimistic guess.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.discovery.skills import AI_SKILLS, extract_skills
from app.discovery.text import sentence_around

# ---------- role family ----------

_EXCLUDE_TITLE = re.compile(
    r"\b(manager|director|head of|vp|vice president|chief|recruit\w*|sales|account|marketing|designer|intern(ship)?|"
    r"analyst|front[- ]?end|ios|android|mobile|support|customer|solutions? (engineer|architect|consultant)|"
    r"field|counsel|finance|legal|people|talent|writer|qa|quality|test|sdet|security|site reliability|sre|"
    r"devops|network|hardware|embedded|firmware|research (scientist|engineer)|scientist|data engineer|"
    r"analytics|product owner|program|project|consultant|trainer|tutor|annotat\w*|ai trainer|evaluator|"
    r"werkstudent|praktikum|student|graduate|new grad|fresher|entry[- ]level|apprentice|ausbildung)\b",
    re.IGNORECASE,
)
_ENGINEER = re.compile(r"\b(engineer|engineering|developer|programmer|swe|sde|entwickler)\b", re.IGNORECASE)
_AI_TITLE = re.compile(
    r"\b(ai|a\.i\.|ml|machine learning|llm|llms|gen ?ai|generative|agentic|agents?|nlp|applied ai|mlops|deep learning)\b",
    re.IGNORECASE,
)
_BACKEND_TITLE = re.compile(
    r"\b(back[- ]?end|server|platform|api|software|full[- ]?stack|java|microservices?|distributed systems|"
    r"infrastructure|integrations?|sde|swe)\b",
    re.IGNORECASE,
)
_JAVA_JD = re.compile(r"\bjava\b(?!\s*script)|\bspring\s*boot\b|\bjvm\b|\bkotlin\b", re.IGNORECASE)

ROLE_FAMILIES = ("ai_engineer", "ai_backend", "java_backend", "backend")


def role_family(title: str, description: str) -> str | None:
    """None means 'not a role we target' and the job is dropped."""
    if _EXCLUDE_TITLE.search(title) or not _ENGINEER.search(title):
        return None
    if _AI_TITLE.search(title):
        return "ai_engineer"
    if not _BACKEND_TITLE.search(title):
        return None
    ai_terms = len(set(extract_skills(description)) & AI_SKILLS - {"machine learning"})
    if ai_terms >= 2:
        return "ai_backend"
    if re.search(r"\bjava\b(?!\s*script)", title, re.IGNORECASE) or len(_JAVA_JD.findall(description)) >= 2:
        return "java_backend"
    return "backend"


_SENIORITY = [
    ("junior", r"\b(junior|jr\.?|associate|entry[- ]level|new grad|fresher|trainee)\b|\b(sde|swe|engineer|developer) ?(i|1)\b(?!\w)"),
    ("principal", r"\b(principal|distinguished|architect)\b"),
    ("staff", r"\bstaff\b"),
    ("lead", r"\b(lead|tech lead)\b"),
    ("senior", r"\b(senior|sr\.?|iii|3)\b"),
    ("mid", r"\b(ii|2|mid)\b"),
]


def seniority(title: str) -> str | None:
    for name, pattern in _SENIORITY:
        if re.search(pattern, title, re.IGNORECASE):
            return name
    return None


# ---------- experience ----------

_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*)?\+?\s*(?:years|yrs|year)",
    re.IGNORECASE,
)


def experience_range(text: str) -> tuple[int | None, int | None]:
    """First plausible 'N+ years' / 'N-M years' mention."""
    for m in _YEARS.finditer(text):
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else None
        if 0 < lo <= 20 and (hi is None or lo <= hi <= 25):
            return lo, hi
    return None, None


# ---------- location ----------

INDIA_CITIES = {
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru", "hyderabad": "Hyderabad", "chennai": "Chennai",
    "pune": "Pune", "mumbai": "Mumbai", "navi mumbai": "Mumbai", "gurugram": "Gurugram", "gurgaon": "Gurugram",
    "noida": "Noida", "new delhi": "Delhi", "delhi": "Delhi", "kolkata": "Kolkata", "ahmedabad": "Ahmedabad",
    "kochi": "Kochi", "coimbatore": "Coimbatore", "jaipur": "Jaipur", "chandigarh": "Chandigarh",
    "thiruvananthapuram": "Thiruvananthapuram", "trivandrum": "Thiruvananthapuram", "indore": "Indore",
    "mysuru": "Mysuru", "mysore": "Mysuru", "nagpur": "Nagpur", "visakhapatnam": "Visakhapatnam",
}
COUNTRIES = {
    "India": r"\bindia\b",
    "United States": r"\bunited states\b|\busa?\b|\bu\.s\.|\bnew york\b|\bsan francisco\b|\bseattle\b|\bcalifornia\b|\b(ny|ca|wa|tx|ma)\b,?\s*(usa?)?$",
    "United Kingdom": r"\bunited kingdom\b|\buk\b|\blondon\b|\bengland\b|\bmanchester\b|\bedinburgh\b",
    "Germany": r"\bgermany\b|\bdeutschland\b|\bberlin\b|\bmunich\b|\bmünchen\b|\bhamburg\b|\bfrankfurt\b|\bcologne\b|\bköln\b",
    "Netherlands": r"\bnetherlands\b|\bamsterdam\b|\brotterdam\b|\butrecht\b|\bthe hague\b|\beindhoven\b",
    "Ireland": r"\bireland\b|\bdublin\b|\bcork\b",
    "Singapore": r"\bsingapore\b",
    "Canada": r"\bcanada\b|\btoronto\b|\bvancouver\b|\bmontreal\b",
    "Australia": r"\baustralia\b|\bsydney\b|\bmelbourne\b",
    "France": r"\bfrance\b|\bparis\b",
    "Spain": r"\bspain\b|\bmadrid\b|\bbarcelona\b",
    "Poland": r"\bpoland\b|\bwarsaw\b|\bkrakow\b",
    "Portugal": r"\bportugal\b|\blisbon\b",
    "Japan": r"\bjapan\b|\btokyo\b",
    "United Arab Emirates": r"\buae\b|\bdubai\b|\babu dhabi\b",
}
RELOCATION_TARGETS = {"Germany", "Netherlands", "Ireland", "United Kingdom", "Singapore"}
_COUNTRY_RX = {c: re.compile(p, re.IGNORECASE) for c, p in COUNTRIES.items()}

_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\bdistributed\b", re.IGNORECASE)
# Not bare "hybrid": RAG and cloud JDs say "hybrid search" / "hybrid cloud".
_HYBRID_JD = re.compile(
    r"\bhybrid (?:work|working|role|model|position|setup|arrangement|schedule|policy|environment)\b|\b(?:role|position) is hybrid\b|\b\d\s*(?:-\d\s*)?days? (?:a|per|each) week (?:in|at|from) (?:the |our )?office|\bin[- ]office\b|\bwork from (?:the |our )?office\b",
    re.IGNORECASE,
)
_OCCASIONAL_OFFICE = re.compile(
    r"\b(once|twice|\d+ times?) (?:a|per) (month|quarter)\b|\bquarterly (?:visits?|offsites?|meet-?ups?)\b|"
    r"\boccasional(?:ly)? (?:travel|visits?|come) to (?:the |our )?office\b",
    re.IGNORECASE,
)
_WORLDWIDE_JD = re.compile(
    r"\bworldwide\b|\banywhere in the world\b|\bwork from anywhere\b|\bglobal(?:ly)? remote\b|\bremote[,\s-]+(?:global|anywhere)\b",
    re.IGNORECASE,
)
# Location strings are short, so a bare "anywhere" there is meaningful.
_WORLDWIDE_LOC = re.compile(_WORLDWIDE_JD.pattern + r"|\banywhere\b|\bglobal\b", re.IGNORECASE)
_REGION_ONLY = re.compile(r"\b(emea|europe|eu|americas|north america|latam|us only|us-based)\b", re.IGNORECASE)
_APAC = re.compile(r"\b(apac|asia|asia[- ]pacific)\b", re.IGNORECASE)
# A place India isn't part of, e.g. "the US", "US / Canada", "the United States or Canada".
_ELSEWHERE = r"(?:the )?(?:us|u\.s\.|usa|united states|canada|uk|united kingdom|eu|europe|north america|latam)"
_ELSEWHERE_SET = rf"{_ELSEWHERE}(?:\s*(?:/|,|or|and|&)\s*{_ELSEWHERE})*"
_US_ONLY_JD = re.compile(
    rf"\b(?:must|required to) (?:be )?(?:located|reside|live|based) in {_ELSEWHERE_SET}\b|"
    rf"\bauthori[sz]ed to work in {_ELSEWHERE_SET}\b|\b(?:us|u\.s\.) citizens? only\b|"
    # Only when it's about the role: legal boilerplate says "...Fair Chance Act, for US-based candidates".
    rf"\b(?:role|position|job|opening|opportunity) (?:is )?(?:only )?(?:for|open to) {_ELSEWHERE_SET}[- ](?:based|located|resident) (?:candidates|applicants)\b|"
    rf"\bonly (?:open to |for )?{_ELSEWHERE_SET}[- ](?:based|located|resident) (?:candidates|applicants)\b|"
    rf"\b{_ELSEWHERE_SET}[- ](?:based|located|resident) (?:candidates|applicants) only\b|"
    rf"\b(?:open|available|limited) (?:only )?to (?:candidates|applicants|residents) (?:who are )?(?:located |based |residing )?in {_ELSEWHERE_SET}\b|"
    rf"\b(?:candidates|applicants) (?:must be )?(?:located|based|residing) in {_ELSEWHERE_SET} only\b",
    re.IGNORECASE,
)
_SPONSOR_YES = re.compile(
    r"\bvisa sponsorship\b|\bsponsor(?:ship)? (?:for |of )?(?:your |a |the )?(?:work )?visas?\b|\bwe (?:will|can|do) sponsor\b|"
    r"\bblue card\b|\bskilled worker visa\b|\bhighly skilled migrant\b|\bkennismigrant\b|"
    r"\bcritical skills employment permit\b|\bwork permit (?:support|sponsorship)\b",
    re.IGNORECASE,
)
# Relocation help alone often means moving within the country, so it doesn't prove visa support.
_RELOCATION_ONLY = re.compile(
    r"\brelocation (?:support|assistance|package|bonus|budget)\b|\bhelp(?:ing)? you relocate\b", re.IGNORECASE
)
_SPONSOR_NO = re.compile(
    r"\b(?:no|not|unable to|cannot|can't|don't|do not|will not|won't|are not able to)\s+(?:currently\s+)?"
    r"(?:provide|offer|support)?\s*(?:visa\s+)?sponsor|\bwithout (?:the need for )?(?:visa )?sponsorship\b|"
    r"\bsponsorship (?:is )?not (?:available|provided|offered)\b|\bmust (?:already )?have (?:the )?right to work\b",
    re.IGNORECASE,
)


@dataclass
class LocationHints:
    """What a source tells us beyond the free-text location."""

    remote: bool | None = None           # explicit remote flag
    hybrid: bool | None = None           # explicit hybrid flag
    country_codes: list[str] = field(default_factory=list)  # ISO2, e.g. ["IN"]
    location_restrictions: list[str] | None = None  # Himalayas: [] = worldwide
    visa_sponsorship: bool | None = None  # Arbeitnow visa filter


@dataclass
class Placement:
    segment: str | None  # None = out of scope, drop
    arrangement: str
    countries: list[str]
    cities: list[str]
    eligibility: dict[str, Any]
    evidence: dict[str, str]


def _find(rx: re.Pattern, text: str) -> str | None:
    m = rx.search(text)
    return sentence_around(text, m.start(), m.end()) if m else None


def place(location: str, description: str, hints: LocationHints | None = None) -> Placement:
    hints = hints or LocationHints()
    loc = location or ""
    loc_l = loc.lower()
    cities = sorted({canon for alias, canon in INDIA_CITIES.items() if re.search(rf"\b{alias}\b", loc_l)})
    countries = sorted({c for c, rx in _COUNTRY_RX.items() if rx.search(loc)})
    if "IN" in hints.country_codes or cities:
        countries = sorted(set(countries) | {"India"})
    evidence: dict[str, str] = {}
    is_remote = hints.remote is True or bool(_REMOTE.search(loc))
    if hints.remote is True:
        evidence["remote"] = "Source marks this job as remote"
    elif is_remote:
        evidence["remote"] = f"Location: {loc}"

    # ----- India -----
    if "India" in countries:
        if not is_remote:
            hybrid_jd = _find(_HYBRID_JD, description)
            if hints.hybrid or "hybrid" in loc_l:
                evidence["arrangement"] = "Source marks this job as hybrid"
                arrangement = "hybrid"
            elif hybrid_jd:
                evidence["arrangement"] = hybrid_jd
                arrangement = "hybrid"
            else:
                arrangement = "onsite" if hints.remote is False else "unknown"
            return Placement("IN_ONSITE_HYBRID", arrangement, countries, cities, {}, evidence)

        # Remote in India: check office expectations before calling it fully remote.
        hybrid_jd = _find(_HYBRID_JD, description)
        occasional = _find(_OCCASIONAL_OFFICE, description)
        if hints.hybrid or "hybrid" in loc_l or hybrid_jd:
            evidence["arrangement"] = hybrid_jd or "Source marks this job as hybrid"
            return Placement("IN_ONSITE_HYBRID", "hybrid", countries, cities, {}, evidence)
        if occasional:
            evidence["arrangement"] = occasional
            return Placement("IN_REMOTE", "remote_occasional_office", countries, cities, {}, evidence)
        if cities:
            evidence["arrangement"] = f"Remote, but location names {', '.join(cities)}: {loc}"
            return Placement("IN_REMOTE", "remote_city_restricted", countries, cities, {}, evidence)
        evidence["arrangement"] = f"Listed as remote with allowed location India ({loc or 'source country = India'}); no office requirement found in the posting"
        return Placement("IN_REMOTE", "fully_remote", countries, cities, {}, evidence)

    # ----- International remote: India eligibility must be verified -----
    if is_remote:
        eligibility, why = _remote_eligibility(loc, description, hints)
        evidence["eligibility"] = why
        arrangement = "fully_remote"
        if eligibility["india_eligible"] == "verified_yes":
            return Placement("INTL_REMOTE", arrangement, countries, cities, eligibility, evidence)
        if eligibility["india_eligible"] == "unverified":
            return Placement("UNVERIFIED", arrangement, countries, cities, eligibility, evidence)
        return Placement(None, arrangement, countries, cities, eligibility, evidence)

    # ----- International onsite: only with explicit sponsorship -----
    sponsor_no = _find(_SPONSOR_NO, description)
    sponsor_yes = _find(_SPONSOR_YES, description)
    arrangement = "hybrid" if hints.hybrid or "hybrid" in loc_l or _HYBRID_JD.search(description) else "onsite"
    if sponsor_no:
        evidence["visa"] = sponsor_no
        return Placement(None, arrangement, countries, cities, {"visa_sponsorship": "no"}, evidence)
    if sponsor_yes or hints.visa_sponsorship:
        evidence["visa"] = sponsor_yes or "Listed under the source's visa-sponsorship filter"
        return Placement("INTL_RELOCATION", arrangement, countries, cities, {"visa_sponsorship": "yes"}, evidence)
    relocation_only = _find(_RELOCATION_ONLY, description)
    if relocation_only:
        evidence["visa"] = f"Relocation help offered, but visa sponsorship isn't mentioned: {relocation_only}"
        return Placement("UNVERIFIED", arrangement, countries, cities, {"visa_sponsorship": "unknown"}, evidence)
    if set(countries) & RELOCATION_TARGETS:
        evidence["visa"] = "Posting doesn't mention visa sponsorship either way"
        return Placement("UNVERIFIED", arrangement, countries, cities, {"visa_sponsorship": "unknown"}, evidence)
    return Placement(None, arrangement, countries, cities, {}, evidence)


def _remote_eligibility(loc: str, description: str, hints: LocationHints) -> tuple[dict[str, Any], str]:
    restrictions = hints.location_restrictions
    if restrictions is not None:
        if not restrictions:
            return {"india_eligible": "verified_yes", "scope": "worldwide"}, "Source lists no location restriction (worldwide)"
        if any(r.lower() == "india" for r in restrictions):
            return {"india_eligible": "verified_yes", "scope": "country_list"}, f"Allowed locations include India: {', '.join(restrictions)}"
        return {"india_eligible": "verified_no", "scope": "country_list"}, f"Allowed locations exclude India: {', '.join(restrictions)}"

    if hints.country_codes and "IN" not in hints.country_codes:
        return {"india_eligible": "verified_no", "scope": "single_country"}, f"Source lists country: {', '.join(hints.country_codes)}"
    us_only = _find(_US_ONLY_JD, description)
    if us_only:
        return {"india_eligible": "verified_no", "scope": "single_country"}, us_only
    if re.search(r"\bindia\b", loc, re.IGNORECASE):
        return {"india_eligible": "verified_yes", "scope": "country_list"}, f"Location names India: {loc}"
    named = set(c for c, rx in _COUNTRY_RX.items() if rx.search(loc)) - {"India"}
    worldwide_jd = _find(_WORLDWIDE_JD, description)
    if _WORLDWIDE_LOC.search(loc):
        # "Global - Remote; United States" often means remote within the named country only.
        if named or _REGION_ONLY.search(loc):
            if worldwide_jd:
                return {"india_eligible": "verified_yes", "scope": "worldwide"}, worldwide_jd
            return {"india_eligible": "unverified", "scope": "unknown"}, (
                f"Location says global but also names a country, which often means remote only there: {loc}"
            )
        return {"india_eligible": "verified_yes", "scope": "worldwide"}, f"Location: {loc}"
    if _REGION_ONLY.search(loc) or named:
        return {"india_eligible": "verified_no", "scope": "region"}, f"Location restricted to: {loc}"
    india_jd = _find(re.compile(r"\b(remote|anywhere) (?:in|from) india\b|\bindia\b", re.IGNORECASE), description)
    if worldwide_jd:
        return {"india_eligible": "verified_yes", "scope": "worldwide"}, worldwide_jd
    if _APAC.search(loc):
        return {"india_eligible": "unverified", "scope": "region"}, f"APAC/Asia doesn't always include India: {loc}"
    if india_jd:
        return {"india_eligible": "unverified", "scope": "unknown"}, f"India is mentioned, but not clearly as an allowed location: {india_jd}"
    return {"india_eligible": "unverified", "scope": "unknown"}, f"Remote with no stated location rules: {loc or '(blank)'}"
