import pytest
from pydantic import ValidationError

from app import prefs


def test_default_weights_match_the_brief():
    w = prefs.OpportunityWeights()
    assert sum(w.model_dump().values()) == 100
    assert w.work_life_balance == 20


def test_weights_must_sum_to_100():
    with pytest.raises(ValidationError, match="sum to 100"):
        prefs.OpportunityWeights(technical_match=50)


def test_allocation_must_sum_to_100():
    with pytest.raises(ValidationError):
        prefs.CompanyAllocation(medium=70, large=30, highly_competitive=10)


def test_round_trip_and_defaults(session):
    assert prefs.get_section(session, "compensation").target_lpa == 22
    prefs.put_section(session, "company_allocation", {"medium": 50, "large": 40, "highly_competitive": 10})
    assert prefs.get_section(session, "company_allocation").large == 40
    assert prefs.get_all(session)["company_allocation"]["medium"] == 50
