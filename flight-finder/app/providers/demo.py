"""Offline demo source.

Generates realistic-looking but made-up flights so the whole app works with no
network access or API keys. The same spec always gives the same flights, which
keeps the UI and tests predictable.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import random
from typing import Optional

from ..models import FlightOffer, Leg, SearchRequest
from .base import FlightProvider

AIRLINES = [
    ("AA", "American Airlines"),
    ("BA", "British Airways"),
    ("DL", "Delta Air Lines"),
    ("UA", "United Airlines"),
    ("LH", "Lufthansa"),
    ("AF", "Air France"),
    ("EK", "Emirates"),
    ("QR", "Qatar Airways"),
    ("AI", "Air India"),
    ("SQ", "Singapore Airlines"),
]

HUBS = ["DXB", "DOH", "FRA", "LHR", "CDG", "AMS", "ORD", "ATL", "SIN", "IST"]

CABIN_MULTIPLIER = {"economy": 1.0, "premium_economy": 1.7, "business": 3.6, "first": 6.0}

# Rough exchange rates from USD, good enough for demo prices.
FX = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "INR": 83.0, "CAD": 1.36, "AUD": 1.52}


def _rng(*parts: object) -> random.Random:
    seed = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def _route_base_minutes(origin: str, destination: str) -> int:
    # A stable pseudo "distance" for the pair, between 1h and 15h non-stop.
    r = _rng("route", *sorted((origin, destination)))
    return r.randint(60, 900)


class DemoProvider(FlightProvider):
    name = "demo"
    label = "Demo data (offline)"
    description = "Made-up but realistic flights. Works without internet or API keys."

    def notes(self, req: SearchRequest) -> list[str]:
        return ["Demo data: these flights are made up, for trying the app out."]

    async def search(self, req: SearchRequest) -> list[FlightOffer]:
        base = _route_base_minutes(req.origin, req.destination)
        fx = FX.get(req.currency, 1.0)
        currency = req.currency if req.currency in FX else "USD"
        r = _rng(req.origin, req.destination, req.depart_date, req.return_date, req.cabin)

        offers: list[FlightOffer] = []
        for i in range(r.randint(14, 24)):
            code, airline = r.choice(AIRLINES)
            out = self._leg(r, code, airline, req.origin, req.destination, req.depart_date, base)
            back: Optional[Leg] = None
            if req.return_date:
                back = self._leg(
                    r, code, airline, req.destination, req.origin, req.return_date, base
                )
            stops_total = out.stops + (back.stops if back else 0)
            usd = (
                (60 + base * r.uniform(0.35, 0.6))
                * (1.9 if back else 1.0)
                * CABIN_MULTIPLIER[req.cabin]
                * (1.0 - 0.08 * stops_total)
            )
            price = round(usd * fx * req.adults, 2)
            offers.append(
                FlightOffer(
                    provider=self.name,
                    price=price,
                    currency=currency,
                    outbound=out,
                    inbound=back,
                    booking_url=None,
                )
            )
        return offers

    @staticmethod
    def _leg(
        r: random.Random,
        code: str,
        airline: str,
        origin: str,
        destination: str,
        day: dt.date,
        base_minutes: int,
    ) -> Leg:
        stops = r.choices([0, 1, 2], weights=[45, 40, 15])[0]
        if base_minutes < 150:
            stops = min(stops, 1)
        layovers = sum(r.randint(50, 240) for _ in range(stops))
        duration = int(base_minutes * (1 + 0.12 * stops)) + layovers
        depart = dt.datetime.combine(day, dt.time(r.randint(0, 23), r.choice([0, 15, 30, 45])))
        arrive = depart + dt.timedelta(minutes=duration)
        numbers = [f"{code}{r.randint(10, 9999)}" for _ in range(stops + 1)]
        via = r.sample([h for h in HUBS if h not in (origin, destination)], stops)
        return Leg(
            origin=origin,
            destination=destination,
            depart_at=depart,
            arrive_at=arrive,
            duration_minutes=duration,
            stops=stops,
            flight_numbers=numbers,
            via=via,
            airline=airline,
            airline_code=code,
        )
