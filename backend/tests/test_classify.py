import pytest

from app.discovery.classify import LocationHints, experience_range, place, role_family, seniority
from app.discovery.skills import extract_skills

AI_JD = "You will build RAG pipelines with embeddings and a vector database, and ship LLM features."
JAVA_JD = "We use Java 17 and Spring Boot microservices on AWS. Strong Java skills required."


@pytest.mark.parametrize("title, jd, expected", [
    ("Senior AI Engineer", "", "ai_engineer"),
    ("LLM Application Developer", "", "ai_engineer"),
    ("Generative AI Engineer", "", "ai_engineer"),
    ("Senior Backend Engineer", AI_JD, "ai_backend"),
    ("Senior Software Engineer", JAVA_JD, "java_backend"),
    ("Java Developer", "", "java_backend"),
    ("Backend Engineer", "We use Go and Postgres.", "backend"),
    ("Engineering Manager, AI Platform", AI_JD, None),
    ("Frontend Engineer", "", None),
    ("Solutions Engineer", "", None),
    ("Account Executive", "", None),
    ("Research Scientist, LLMs", "", None),
    ("AI Trainer - Software Engineering", "", None),
    ("Product Designer", "", None),
    ("Software Engineer, New Grad", "", None),
])
def test_role_family(title, jd, expected):
    assert role_family(title, jd) == expected


@pytest.mark.parametrize("title, expected", [
    ("Senior Backend Engineer", "senior"), ("Sr. Java Developer", "senior"), ("Staff Engineer", "staff"),
    ("Principal Engineer", "principal"), ("Software Engineer II", "mid"), ("Software Engineer I", "junior"),
    ("Junior Developer", "junior"), ("Backend Engineer", None),
])
def test_seniority(title, expected):
    assert seniority(title) == expected


@pytest.mark.parametrize("text, expected", [
    ("You have 5+ years of experience", (5, None)),
    ("6-10 years in backend development", (6, 10)),
    ("3 to 5 yrs", (3, 5)),
    ("Founded 150 years ago", (None, None)),
    ("No experience mentioned", (None, None)),
])
def test_experience_range(text, expected):
    assert experience_range(text) == expected


def test_skills_avoid_common_false_positives():
    assert "rest apis" not in extract_skills("Join the rest of the team")
    assert "spring" not in extract_skills("Joining in spring 2027")
    assert "java" not in extract_skills("JavaScript and TypeScript")
    assert {"rag", "embeddings", "vector databases", "llms"} <= set(extract_skills(AI_JD))


# ---------- placement: the rules that decide the dashboard tab ----------

def test_india_onsite():
    p = place("Bengaluru, India", "Work at our Bengaluru office.")
    assert (p.segment, p.arrangement, p.cities) == ("IN_ONSITE_HYBRID", "unknown", ["Bengaluru"])


def test_india_hybrid_from_jd_is_never_remote():
    p = place("Remote - India", "This is a hybrid role: 3 days a week in the office.")
    assert p.segment == "IN_ONSITE_HYBRID" and p.arrangement == "hybrid"
    assert "3 days a week" in p.evidence["arrangement"]


def test_hybrid_search_is_not_a_hybrid_work_arrangement():
    p = place("Remote, India", "Build hybrid search over our vector index and hybrid cloud infra.")
    assert (p.segment, p.arrangement) == ("IN_REMOTE", "fully_remote")


def test_india_remote_city_restricted():
    p = place("Remote - Bengaluru", "")
    assert (p.segment, p.arrangement) == ("IN_REMOTE", "remote_city_restricted")


def test_india_remote_with_quarterly_visits():
    p = place("India (Remote)", "Fully remote, with team meetups once a quarter at the office.")
    assert (p.segment, p.arrangement) == ("IN_REMOTE", "remote_occasional_office")


def test_india_remote_from_source_flags():
    p = place("Hyderabad", "", LocationHints(remote=True, country_codes=["IN"]))
    assert (p.segment, p.arrangement) == ("IN_REMOTE", "remote_city_restricted")


def test_intl_remote_worldwide_verified():
    p = place("Remote - Worldwide", "")
    assert p.segment == "INTL_REMOTE" and p.eligibility["india_eligible"] == "verified_yes"


def test_intl_remote_us_only_is_dropped():
    assert place("Remote - US", "").segment is None
    assert place("Remote", "Candidates must be located in the United States.").segment is None


@pytest.mark.parametrize("jd", [
    "This is a remote role for US / Canada based candidates.",
    "Applicants must be located in the United States or Canada.",
    "The role is open only to candidates based in the UK.",
    "You must be authorized to work in the US.",
])
def test_intl_remote_other_country_wording_is_dropped(jd):
    assert place("Remote", jd).segment is None


def test_global_location_naming_a_country_is_unverified():
    p = place("Global - Remote; United States", "Build evaluation infrastructure.")
    assert p.segment == "UNVERIFIED" and "names a country" in p.evidence["eligibility"]
    assert place("Global - Remote; United States", "We hire from anywhere in the world.").segment == "INTL_REMOTE"


@pytest.mark.parametrize("jd", [
    "We have offices in the US and Canada.",
    "We comply with the California Fair Chance Act, for US-based candidates.",
])
def test_mentions_of_the_us_are_not_a_restriction(jd):
    assert place("Remote - Worldwide", jd).segment == "INTL_REMOTE"


def test_intl_remote_unclear_goes_to_unverified():
    p = place("Remote", "Join our distributed team.")
    assert p.segment == "UNVERIFIED" and p.eligibility["india_eligible"] == "unverified"


def test_apac_is_not_assumed_to_include_india():
    assert place("Remote - APAC", "").segment == "UNVERIFIED"


def test_himalayas_restrictions():
    assert place("Worldwide", "", LocationHints(remote=True, location_restrictions=[])).segment == "INTL_REMOTE"
    assert place("United States", "", LocationHints(remote=True, location_restrictions=["United States"])).segment is None


def test_source_country_hint_excludes_india():
    assert place("Remote", "", LocationHints(remote=True, country_codes=["US"])).segment is None


def test_relocation_needs_explicit_sponsorship():
    p = place("Berlin, Germany", "We offer visa sponsorship and relocation support.")
    assert p.segment == "INTL_RELOCATION" and "visa sponsorship" in p.evidence["visa"].lower()


def test_no_sponsorship_wins():
    assert place("Amsterdam, Netherlands", "We are unable to sponsor visas. Relocation support available.").segment is None


def test_relocation_target_without_mention_is_unverified():
    p = place("Dublin, Ireland", "Great team.")
    assert p.segment == "UNVERIFIED" and p.eligibility["visa_sponsorship"] == "unknown"


def test_other_country_onsite_without_sponsorship_is_dropped():
    assert place("San Francisco, CA", "Great team.").segment is None


def test_relocation_assistance_alone_is_not_visa_sponsorship():
    p = place("San Francisco, CA", "Hybrid, 3 days in office. Relocation assistance is available to new employees.")
    assert p.segment == "UNVERIFIED" and "visa sponsorship isn't mentioned" in p.evidence["visa"]
