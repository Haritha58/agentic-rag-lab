"""Salary extraction. Only figures actually present in the posting are used.

Output shape (stored in jobs.salary):
  {currency, min, max, period: "year", provenance, source_text, inr_min, inr_max, fx_rate, fx_date}
or {"provenance": "not_disclosed"}. Nothing here estimates; estimates come later and are labelled.
"""

import re
from typing import Any

from app.discovery.text import sentence_around

_LPA = re.compile(
    r"(?:₹|inr|rs\.?)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:-|–|—|to)\s*(?:₹|inr|rs\.?)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?)\b",
    re.IGNORECASE,
)
_SYMBOL = {"$": "USD", "€": "EUR", "£": "GBP", "s$": "SGD", "₹": "INR"}
_NUM = r"(\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)\s*([kK])?"
_CUR = r"(\$|€|£|S\$|₹|USD|EUR|GBP|SGD|CAD|AUD|CHF|INR)"
_RANGE = re.compile(rf"{_CUR}\s?{_NUM}\s*(?:-|–|—|to)\s*{_CUR}?\s?{_NUM}(?:\s*{_CUR})?", re.IGNORECASE)
_HOURLY = re.compile(r"per hour|/\s*h(ou)?r|hourly|an hour", re.IGNORECASE)


def _amount(num: str, k: str | None) -> float:
    digits = re.sub(r"[,.](?=\d{3}\b)", "", num)
    value = float(digits)
    return value * 1000 if k else value


def _currency(token: str | None) -> str | None:
    if not token:
        return None
    return _SYMBOL.get(token.lower(), token.upper())


def from_text(text: str) -> dict[str, Any] | None:
    m = _LPA.search(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if 1 <= lo <= hi <= 300:
            return {
                "currency": "INR", "min": lo * 100_000, "max": hi * 100_000, "period": "year",
                "provenance": "verified_posting", "source_text": sentence_around(text, m.start(), m.end(), 80),
            }
    # groups: 1 currency, 2 low, 3 low-k, 4 currency again, 5 high, 6 high-k, 7 trailing currency
    for m in _RANGE.finditer(text):
        cur = _currency(m.group(1))
        trailing = _currency(m.group(7))
        if trailing and m.group(1) == "$":  # "$100k - $150k CAD"
            cur = trailing
        k = m.group(3) or m.group(6)  # "100-150k" means both ends are thousands
        lo, hi = _amount(m.group(2), k), _amount(m.group(5), k)
        context = text[max(0, m.start() - 60): m.end() + 60]
        if _HOURLY.search(context) or not (10_000 <= lo <= hi <= 2_000_000):
            continue
        return {
            "currency": cur, "min": lo, "max": hi, "period": "year",
            "provenance": "verified_posting", "source_text": sentence_around(text, m.start(), m.end(), 80),
        }
    return None


def from_struct(currency: str | None, lo: float | None, hi: float | None, period: str | None) -> dict[str, Any] | None:
    """Structured salary fields from a source API (Lever, Ashby, Himalayas, RemoteOK)."""
    if not currency or not lo:
        return None
    hi = hi or lo
    p = (period or "year").lower()
    if any(x in p for x in ("hour", "day", "week")):
        return None  # contract rates; not comparable to annual CTC
    if "month" in p:
        lo, hi = lo * 12, hi * 12
    return {"currency": currency.upper(), "min": float(lo), "max": float(hi), "period": "year",
            "provenance": "verified_posting", "source_text": "Structured salary field from the job board"}


def with_inr(salary: dict[str, Any] | None, rates: dict[str, float], fx_date: str | None) -> dict[str, Any]:
    """Adds INR conversion. `rates` maps currency -> INR per 1 unit."""
    if not salary:
        return {"provenance": "not_disclosed"}
    cur = salary["currency"]
    rate = 1.0 if cur == "INR" else rates.get(cur)
    if rate is None:
        return {**salary, "inr_min": None, "inr_max": None, "fx_rate": None, "fx_date": None}
    return {**salary, "inr_min": round(salary["min"] * rate), "inr_max": round(salary["max"] * rate),
            "fx_rate": rate, "fx_date": fx_date if cur != "INR" else None}
