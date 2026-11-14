"""Real fares from the Travelpayouts (Aviasales) Data API.

Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163

Free with a Travelpayouts account token. Prices are real fares that Aviasales
users found in the last 48 hours (a cache, not a live search), so a fare can be
a day or two old and quiet routes or dates may have no data. Economy only.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Optional

import httpx

from ..models import FlightOffer, Leg, SearchRequest
from .base import FlightProvider, ProviderError

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
AIRLINES_URL = "https://api.travelpayouts.com/data/en/airlines.json"
SITE = "https://www.aviasales.com"

_airline_names: Optional[dict[str, str]] = None


async def _load_airline_names(client: httpx.AsyncClient) -> dict[str, str]:
    """IATA code -> airline name, fetched once from Travelpayouts' public data."""
    global _airline_names
    if _airline_names is None:
        try:
            resp = await client.get(AIRLINES_URL, timeout=15)
            resp.raise_for_status()
            _airline_names = {
                a["code"]: a.get("name") or a.get("name_translations", {}).get("en") or a["code"]
                for a in resp.json()
                if a.get("code")
            }
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return {}  # names are cosmetic; try again on the next search
    return _airline_names


def _local(value: str) -> dt.datetime:
    """Keep the airport's local wall-clock time, drop the UTC offset."""
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _leg(
    origin: str,
    destination: str,
    depart: dt.datetime,
    minutes: int,
    stops: int,
    code: str,
    names: dict[str, str],
    flight_number: Optional[str],
) -> Leg:
    return Leg(
        origin=origin,
        destination=destination,
        depart_at=depart,
        arrive_at=depart + dt.timedelta(minutes=minutes),
        duration_minutes=minutes,
        stops=stops,
        flight_numbers=[f"{code}{flight_number}"] if flight_number else [],
        airline=names.get(code, code or "Unknown"),
        airline_code=code,
    )


def parse_offers(
    payload: dict, adults: int, currency: str, names: dict[str, str]
) -> list[FlightOffer]:
    offers: list[FlightOffer] = []
    for item in payload.get("data") or []:
        try:
            code = item.get("airline") or ""
            fn = str(item["flight_number"]) if item.get("flight_number") else None
            origin = item.get("origin_airport") or item["origin"]
            dest = item.get("destination_airport") or item["destination"]
            out_minutes = int(item.get("duration_to") or item.get("duration") or 0)
            outbound = _leg(
                origin, dest, _local(item["departure_at"]), out_minutes,
                int(item.get("transfers") or 0), code, names, fn,
            )
            inbound = None
            if item.get("return_at"):
                inbound = _leg(
                    dest, origin, _local(item["return_at"]),
                    int(item.get("duration_back") or 0),
                    int(item.get("return_transfers") or 0), code, names, None,
                )
            link = item.get("link")
            offers.append(
                FlightOffer(
                    provider="travelpayouts",
                    price=round(float(item["price"]) * adults, 2),
                    currency=(payload.get("currency") or currency).upper(),
                    outbound=outbound,
                    inbound=inbound,
                    booking_url=f"{SITE}{link}" if link else None,
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return offers


class TravelpayoutsProvider(FlightProvider):
    name = "travelpayouts"
    label = "Aviasales prices (free, last 48h)"
    description = (
        "Real fares found on Aviasales in the last 48 hours. Free; needs TRAVELPAYOUTS_TOKEN."
    )

    def available(self) -> bool:
        return bool(os.environ.get("TRAVELPAYOUTS_TOKEN"))

    def build_params(self, req: SearchRequest) -> dict:
        params = {
            "origin": req.origin,
            "destination": req.destination,
            "departure_at": req.depart_date.isoformat(),
            "currency": req.currency.lower(),
            "sorting": "price",
            "limit": 100,
            "one_way": "false" if req.return_date else "true",
            "direct": "true" if req.max_stops == 0 else "false",
        }
        if req.return_date:
            params["return_at"] = req.return_date.isoformat()
        return params

    def notes(self, req: SearchRequest) -> list[str]:
        notes = [
            "Aviasales prices are real fares seen in the last 48 hours, not a live search. "
            "Check the price on the booking page.",
            "Arrival times are estimated from flight duration, in the departure airport's time.",
        ]
        if req.adults > 1:
            notes.append(f"Prices are the per-person fare times {req.adults} adults.")
        if req.cabin != "economy":
            notes.append("Aviasales data covers economy fares only.")
        return notes

    async def search(self, req: SearchRequest) -> list[FlightOffer]:
        token = os.environ.get("TRAVELPAYOUTS_TOKEN")
        if not token:
            raise ProviderError(
                "Travelpayouts is not configured. Set TRAVELPAYOUTS_TOKEN and restart the server."
            )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    API_URL,
                    params=self.build_params(req),
                    headers={"X-Access-Token": token, "Accept-Encoding": "gzip"},
                )
                names = await _load_airline_names(client)
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach Travelpayouts: {e}") from e
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400 or body.get("success") is False:
            msg = body.get("error") or body.get("message") or resp.text[:200]
            raise ProviderError(f"Travelpayouts returned {resp.status_code}: {msg}")
        return parse_offers(body, req.adults, req.currency, names)
