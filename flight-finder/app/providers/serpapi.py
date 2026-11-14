"""Live Google Flights results through SerpApi (https://serpapi.com/google-flights-api).

The free SerpApi plan allows 250 searches a month (50 an hour), and each search
in this app uses one. For round trips Google Flights first lists outbound
flights with the round-trip total price; fetching each return option would
cost an extra search, so the app shows the outbound flight and the
round-trip price, and links to Google Flights to choose the return flight.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Optional

import httpx

from ..models import FlightOffer, Leg, SearchRequest
from .base import FlightProvider, ProviderError

API_URL = "https://serpapi.com/search.json"

TRAVEL_CLASS = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}
SORT_BY = {"price": 2, "departure": 3, "duration": 5}
# app max_stops -> SerpApi "stops" (0 any, 1 nonstop, 2 <=1 stop, 3 <=2 stops)
STOPS = {0: 1, 1: 2, 2: 3}


def _time(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M")


def _code(flight_number: Optional[str]) -> str:
    return (flight_number or "").split(" ")[0]


def _leg(item: dict) -> Leg:
    segments = item["flights"]
    first, last = segments[0], segments[-1]
    depart = _time(first["departure_airport"]["time"])
    arrive = _time(last["arrival_airport"]["time"])
    minutes = item.get("total_duration") or int((arrive - depart).total_seconds() // 60)
    return Leg(
        origin=first["departure_airport"]["id"],
        destination=last["arrival_airport"]["id"],
        depart_at=depart,
        arrive_at=arrive,
        duration_minutes=int(minutes),
        stops=len(segments) - 1,
        via=[l.get("id", "") for l in item.get("layovers") or []],
        flight_numbers=[(s.get("flight_number") or "").replace(" ", "") for s in segments],
        airline=first.get("airline") or "Unknown",
        airline_code=_code(first.get("flight_number")),
    )


def parse_offers(payload: dict, currency: str) -> list[FlightOffer]:
    url = (payload.get("search_metadata") or {}).get("google_flights_url")
    offers: list[FlightOffer] = []
    for item in (payload.get("best_flights") or []) + (payload.get("other_flights") or []):
        try:
            if item.get("price") is None:
                continue  # Google sometimes lists flights without a price
            offers.append(
                FlightOffer(
                    provider="serpapi",
                    price=float(item["price"]),
                    currency=currency,
                    outbound=_leg(item),
                    inbound=None,
                    booking_url=url,
                )
            )
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return offers


class SerpApiProvider(FlightProvider):
    name = "serpapi"
    label = "Google Flights live (SerpApi, 250/month free)"
    description = (
        "Live Google Flights prices via SerpApi. Each search uses 1 of the free plan's "
        "250 monthly searches. Needs SERPAPI_API_KEY."
    )

    def available(self) -> bool:
        return bool(os.environ.get("SERPAPI_API_KEY"))

    def build_params(self, req: SearchRequest) -> dict:
        params: dict = {
            "engine": "google_flights",
            "departure_id": req.origin,
            "arrival_id": req.destination,
            "outbound_date": req.depart_date.isoformat(),
            "type": 1 if req.return_date else 2,
            "adults": req.adults,
            "travel_class": TRAVEL_CLASS[req.cabin],
            "currency": req.currency,
            "hl": "en",
            "sort_by": SORT_BY[req.sort_by],
        }
        if req.return_date:
            params["return_date"] = req.return_date.isoformat()
        if req.max_stops is not None:
            params["stops"] = STOPS.get(req.max_stops, 0)
        if req.max_price is not None:
            params["max_price"] = int(req.max_price)
        if req.airlines:
            params["include_airlines"] = ",".join(req.airlines)
        return params

    def notes(self, req: SearchRequest) -> list[str]:
        notes = ["Live Google Flights prices. This search used 1 of your SerpApi searches."]
        if req.return_date:
            notes.append(
                "Prices are round-trip totals. Pick the return flight on Google Flights "
                "with the Book link."
            )
        return notes

    async def search(self, req: SearchRequest) -> list[FlightOffer]:
        key = os.environ.get("SERPAPI_API_KEY")
        if not key:
            raise ProviderError(
                "SerpApi is not configured. Set SERPAPI_API_KEY and restart the server."
            )
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(API_URL, params={**self.build_params(req), "api_key": key})
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach SerpApi: {e}") from e
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400 or body.get("error"):
            msg = body.get("error") or resp.text[:200]
            if "hasn't returned any results" in str(msg):
                return []
            raise ProviderError(f"SerpApi returned {resp.status_code}: {msg}")
        return parse_offers(body, req.currency)
