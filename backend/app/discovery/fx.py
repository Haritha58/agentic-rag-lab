"""Exchange rates to INR from Frankfurter (ECB reference rates), cached daily in `settings`."""

from datetime import date

import httpx
from sqlalchemy.orm import Session

from app.models import Setting

CURRENCIES = ("USD", "EUR", "GBP", "SGD", "CAD", "AUD", "CHF")
URL = "https://api.frankfurter.dev/v1/latest"


def fetch_rates(client: httpx.Client) -> tuple[dict[str, float], str]:
    resp = client.get(URL, params={"base": "INR", "symbols": ",".join(CURRENCIES)})
    resp.raise_for_status()
    body = resp.json()
    # Response is "1 INR = x USD"; we want "1 USD = y INR".
    return {cur: round(1 / rate, 4) for cur, rate in body["rates"].items()}, body["date"]


def get_rates(session: Session, client: httpx.Client) -> tuple[dict[str, float], str | None]:
    row = session.get(Setting, "fx")
    if row and row.value.get("fetched_on") == date.today().isoformat():
        return row.value["rates"], row.value["date"]
    try:
        rates, fx_date = fetch_rates(client)
    except httpx.HTTPError:
        # Fall back to the last good rates, keeping their original date visible.
        return (row.value["rates"], row.value["date"]) if row else ({}, None)
    session.merge(Setting(key="fx", value={"rates": rates, "date": fx_date, "fetched_on": date.today().isoformat()}))
    return rates, fx_date
