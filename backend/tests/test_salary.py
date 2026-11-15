import pytest

from app.discovery.salary import from_struct, from_text, with_inr


@pytest.mark.parametrize("text, cur, lo, hi", [
    ("CTC: 25 - 35 LPA", "INR", 2_500_000, 3_500_000),
    ("₹30-40 lakhs per annum", "INR", 3_000_000, 4_000_000),
    ("The base salary range is $180,000—$250,000 USD.", "USD", 180_000, 250_000),
    ("Salary: €70k–90k", "EUR", 70_000, 90_000),
    ("£60,000 - £80,000 per year", "GBP", 60_000, 80_000),
    ("$120k - $150k CAD", "CAD", 120_000, 150_000),
])
def test_from_text(text, cur, lo, hi):
    s = from_text(text)
    assert (s["currency"], s["min"], s["max"], s["provenance"]) == (cur, lo, hi, "verified_posting")


@pytest.mark.parametrize("text", [
    "$40 - $60 per hour",
    "Team of 10-20 engineers",
    "No salary listed.",
])
def test_from_text_ignores_non_salaries(text):
    assert from_text(text) is None


def test_from_struct_annualizes_monthly_and_skips_hourly():
    assert from_struct("EUR", 5000, 6000, "monthly")["max"] == 72_000
    assert from_struct("USD", 50, 70, "hourly") is None
    assert from_struct(None, 100, 200, "year") is None


def test_with_inr():
    s = with_inr({"currency": "USD", "min": 100_000, "max": 120_000}, {"USD": 94.0}, "2026-11-12")
    assert (s["inr_min"], s["inr_max"], s["fx_date"]) == (9_400_000, 11_280_000, "2026-11-12")
    assert with_inr(None, {}, None) == {"provenance": "not_disclosed"}
    inr = with_inr({"currency": "INR", "min": 2_500_000, "max": 3_000_000}, {}, "2026-11-12")
    assert inr["inr_max"] == 3_000_000 and inr["fx_date"] is None
