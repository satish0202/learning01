from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import FlightOffer, SearchRequest


class ProviderError(Exception):
    """A flight source could not answer (bad config, network error, upstream error)."""


class FlightProvider(ABC):
    name: str
    label: str
    description: str

    def available(self) -> bool:
        return True

    @abstractmethod
    async def search(self, req: SearchRequest) -> list[FlightOffer]:
        """Return raw offers for the route and dates.

        Providers may pre-filter when the upstream supports it, but the search
        service always applies every filter in the spec afterwards, so a
        provider never has to.
        """
