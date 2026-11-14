"""Applies the user's flight spec to provider results and stores the outcome."""
from __future__ import annotations

import datetime as dt

from . import db
from .models import FlightOffer, SearchRequest, SearchResult
from .providers import ProviderError, get_provider

MAX_RESULTS = 50


def apply_filters(req: SearchRequest, offers: list[FlightOffer]) -> list[FlightOffer]:
    out = []
    for o in offers:
        if req.max_price is not None and o.price > req.max_price:
            continue
        if req.max_stops is not None and o.max_stops > req.max_stops:
            continue
        t = o.outbound.depart_at.time()
        if req.earliest_departure and t < req.earliest_departure:
            continue
        if req.latest_departure and t > req.latest_departure:
            continue
        if req.airlines and o.outbound.airline_code not in req.airlines:
            continue
        out.append(o)
    return out


def sort_offers(req: SearchRequest, offers: list[FlightOffer]) -> list[FlightOffer]:
    keys = {
        "price": lambda o: (o.price, o.total_minutes),
        "duration": lambda o: (o.total_minutes, o.price),
        "departure": lambda o: (o.outbound.depart_at, o.price),
    }
    return sorted(offers, key=keys[req.sort_by])


async def run_search(req: SearchRequest) -> SearchResult:
    if req.depart_date < dt.date.today():
        raise ValueError("departure date is in the past")
    provider = get_provider(req.provider)
    raw = await provider.search(req)
    notes: list[str] = provider.notes(req)
    mismatched = {o.currency for o in raw if o.currency != req.currency}
    if mismatched:
        notes.append(
            f"Prices are in {', '.join(sorted(mismatched))} as returned by the source; "
            f"the max price filter is compared in that currency."
        )
    matched = sort_offers(req, apply_filters(req, raw))
    if len(raw) and not matched:
        notes.append(f"{len(raw)} flights were found but none matched all your filters.")
    shown = matched[:MAX_RESULTS]
    search_id, created = db.save_search(req, shown, notes, len(raw))
    return SearchResult(
        search_id=search_id,
        created_at=created,
        request=req,
        offers=shown,
        total_found=len(raw),
        notes=notes,
    )


__all__ = ["run_search", "apply_filters", "sort_offers", "ProviderError"]
