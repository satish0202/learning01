"""Request/response models shared by the API, providers and database layer."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Cabin = Literal["economy", "premium_economy", "business", "first"]
SortKey = Literal["price", "duration", "departure"]


class SearchRequest(BaseModel):
    """The flight spec the user types into the web page."""

    origin: str = Field(..., description="3-letter IATA airport code, e.g. JFK")
    destination: str = Field(..., description="3-letter IATA airport code, e.g. LHR")
    depart_date: dt.date
    return_date: Optional[dt.date] = None
    adults: int = Field(1, ge=1, le=9)
    cabin: Cabin = "economy"
    max_price: Optional[float] = Field(None, gt=0)
    max_stops: Optional[int] = Field(None, ge=0, le=3)
    earliest_departure: Optional[dt.time] = None
    latest_departure: Optional[dt.time] = None
    airlines: Optional[list[str]] = Field(
        None, description="Only keep flights operated by these airline IATA codes"
    )
    currency: str = "USD"
    sort_by: SortKey = "price"
    provider: str = "demo"

    @field_validator("origin", "destination")
    @classmethod
    def _iata(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("must be a 3-letter airport code like JFK")
        return v

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("must be a 3-letter currency code like USD")
        return v

    @field_validator("airlines")
    @classmethod
    def _airlines(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if not v:
            return None
        cleaned = [a.strip().upper() for a in v if a.strip()]
        return cleaned or None

    @model_validator(mode="after")
    def _dates(self) -> "SearchRequest":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.return_date and self.return_date < self.depart_date:
            raise ValueError("return date is before departure date")
        return self


class Leg(BaseModel):
    """One direction of a trip (outbound or return)."""

    origin: str
    destination: str
    depart_at: dt.datetime
    arrive_at: dt.datetime
    duration_minutes: int
    stops: int
    via: list[str] = []
    flight_numbers: list[str]
    airline: str
    airline_code: str


class FlightOffer(BaseModel):
    provider: str
    price: float
    currency: str
    outbound: Leg
    inbound: Optional[Leg] = None
    booking_url: Optional[str] = None

    @property
    def max_stops(self) -> int:
        return max(self.outbound.stops, self.inbound.stops if self.inbound else 0)

    @property
    def total_minutes(self) -> int:
        return self.outbound.duration_minutes + (
            self.inbound.duration_minutes if self.inbound else 0
        )


class SearchResult(BaseModel):
    search_id: int
    created_at: dt.datetime
    request: SearchRequest
    offers: list[FlightOffer]
    total_found: int
    notes: list[str] = []


class SearchSummary(BaseModel):
    id: int
    created_at: dt.datetime
    origin: str
    destination: str
    depart_date: dt.date
    return_date: Optional[dt.date]
    adults: int
    provider: str
    result_count: int
    cheapest_price: Optional[float]
    currency: str
