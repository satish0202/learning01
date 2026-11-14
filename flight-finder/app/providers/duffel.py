"""Live flight data from the Duffel API (https://duffel.com/docs/api/offer-requests).

Duffel is an airline-retailing API that explicitly permits automated access, so
we use it instead of scraping airline or OTA websites (most of which forbid
scraping in their terms and block bots). A free test token returns offers from
Duffel's sandbox airline; a live token returns real airline fares.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from typing import Optional

import httpx

from ..models import FlightOffer, Leg, SearchRequest
from .base import FlightProvider, ProviderError

API_URL = "https://api.duffel.com/air/offer_requests"
API_VERSION = "v2"

_DURATION = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?")


def parse_duration(value: Optional[str]) -> Optional[int]:
    """ISO-8601 duration such as 'PT7H35M' or 'P1DT2H' -> minutes."""
    if not value:
        return None
    m = _DURATION.fullmatch(value)
    if not m:
        return None
    d, h, mins = (int(x) if x else 0 for x in m.groups())
    return d * 1440 + h * 60 + mins


def _slice_to_leg(s: dict, owner: dict) -> Leg:
    segments = s.get("segments") or []
    if not segments:
        raise ValueError("slice without segments")
    first, last = segments[0], segments[-1]
    depart = dt.datetime.fromisoformat(first["departing_at"])
    arrive = dt.datetime.fromisoformat(last["arriving_at"])
    minutes = parse_duration(s.get("duration"))
    if minutes is None:
        minutes = int((arrive - depart).total_seconds() // 60)
    carrier = first.get("marketing_carrier") or owner or {}
    return Leg(
        origin=(s.get("origin") or {}).get("iata_code") or first["origin"]["iata_code"],
        destination=(s.get("destination") or {}).get("iata_code")
        or last["destination"]["iata_code"],
        depart_at=depart,
        arrive_at=arrive,
        duration_minutes=minutes,
        stops=len(segments) - 1,
        via=[seg["destination"]["iata_code"] for seg in segments[:-1]],
        flight_numbers=[
            f"{(seg.get('marketing_carrier') or {}).get('iata_code', '')}"
            f"{seg.get('marketing_carrier_flight_number', '')}"
            for seg in segments
        ],
        airline=carrier.get("name") or owner.get("name") or "Unknown",
        airline_code=carrier.get("iata_code") or owner.get("iata_code") or "",
    )


def parse_offers(payload: dict) -> list[FlightOffer]:
    offers: list[FlightOffer] = []
    for o in (payload.get("data") or {}).get("offers", []):
        try:
            owner = o.get("owner") or {}
            slices = o.get("slices") or []
            offers.append(
                FlightOffer(
                    provider="duffel",
                    price=float(o["total_amount"]),
                    currency=o["total_currency"],
                    outbound=_slice_to_leg(slices[0], owner),
                    inbound=_slice_to_leg(slices[1], owner) if len(slices) > 1 else None,
                )
            )
        except (KeyError, IndexError, ValueError, TypeError):
            continue  # skip malformed offers rather than failing the whole search
    return offers


class DuffelProvider(FlightProvider):
    name = "duffel"
    label = "Duffel API (live)"
    description = "Airline fares via the Duffel API. Needs DUFFEL_ACCESS_TOKEN."

    def available(self) -> bool:
        return bool(os.environ.get("DUFFEL_ACCESS_TOKEN"))

    def build_body(self, req: SearchRequest) -> dict:
        slices = [
            {
                "origin": req.origin,
                "destination": req.destination,
                "departure_date": req.depart_date.isoformat(),
            }
        ]
        if req.return_date:
            slices.append(
                {
                    "origin": req.destination,
                    "destination": req.origin,
                    "departure_date": req.return_date.isoformat(),
                }
            )
        body: dict = {
            "slices": slices,
            "passengers": [{"type": "adult"} for _ in range(req.adults)],
            "cabin_class": req.cabin,
        }
        if req.max_stops is not None:
            body["max_connections"] = req.max_stops
        return {"data": body}

    async def search(self, req: SearchRequest) -> list[FlightOffer]:
        token = os.environ.get("DUFFEL_ACCESS_TOKEN")
        if not token:
            raise ProviderError(
                "Duffel is not configured. Set DUFFEL_ACCESS_TOKEN and restart the server."
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Duffel-Version": API_VERSION,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    API_URL,
                    params={"return_offers": "true", "supplier_timeout": 20000},
                    headers=headers,
                    json=self.build_body(req),
                )
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not reach Duffel: {e}") from e
        if resp.status_code >= 400:
            try:
                errs = resp.json().get("errors") or []
                msg = "; ".join(e.get("message", "") for e in errs) or resp.text[:200]
            except ValueError:
                msg = resp.text[:200]
            raise ProviderError(f"Duffel returned {resp.status_code}: {msg}")
        return parse_offers(resp.json())
