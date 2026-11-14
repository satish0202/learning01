"""Flight sources. Each provider turns a SearchRequest into a list of FlightOffers."""
from __future__ import annotations

from .base import FlightProvider, ProviderError
from .demo import DemoProvider
from .duffel import DuffelProvider
from .serpapi import SerpApiProvider
from .travelpayouts import TravelpayoutsProvider

_ALL: dict[str, FlightProvider] = {
    p.name: p
    for p in (DemoProvider(), TravelpayoutsProvider(), SerpApiProvider(), DuffelProvider())
}


def get_provider(name: str) -> FlightProvider:
    try:
        return _ALL[name]
    except KeyError:
        raise ProviderError(f"Unknown flight source '{name}'") from None


def list_providers() -> list[dict]:
    return [
        {
            "name": p.name,
            "label": p.label,
            "available": p.available(),
            "description": p.description,
        }
        for p in _ALL.values()
    ]


__all__ = ["FlightProvider", "ProviderError", "get_provider", "list_providers"]
