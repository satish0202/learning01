import datetime as dt

import httpx
import pytest

from app.models import SearchRequest
from app.providers import serpapi, travelpayouts

DAY = (dt.date.today() + dt.timedelta(days=30)).isoformat()
BACK = (dt.date.today() + dt.timedelta(days=37)).isoformat()

TP_PAYLOAD = {
    "success": True,
    "currency": "usd",
    "data": [
        {
            "origin": "NYC", "destination": "LON",
            "origin_airport": "JFK", "destination_airport": "LHR",
            "price": 412, "airline": "BA", "flight_number": "112",
            "departure_at": f"{DAY}T18:30:00-05:00", "return_at": f"{BACK}T09:15:00+00:00",
            "transfers": 0, "return_transfers": 1,
            "duration": 900, "duration_to": 420, "duration_back": 480,
            "link": "/search/NYC1512LON22121?t=abc",
        },
        {"price": 1, "broken": True},
    ],
}

SERP_PAYLOAD = {
    "search_metadata": {"status": "Success", "google_flights_url": "https://www.google.com/travel/flights?x"},
    "best_flights": [{
        "flights": [
            {"departure_airport": {"id": "JFK", "time": f"{DAY} 08:00"},
             "arrival_airport": {"id": "DUB", "time": f"{DAY} 19:30"},
             "airline": "Aer Lingus", "flight_number": "EI 104"},
            {"departure_airport": {"id": "DUB", "time": f"{DAY} 21:00"},
             "arrival_airport": {"id": "LHR", "time": f"{DAY} 22:20"},
             "airline": "Aer Lingus", "flight_number": "EI 168"},
        ],
        "layovers": [{"duration": 90, "id": "DUB"}],
        "total_duration": 560, "price": 655,
    }],
    "other_flights": [{"flights": [], "price": 300}, {"flights": [{}], "price": None}],
}


def req(**kw):
    base = dict(origin="JFK", destination="LHR", depart_date=DAY, return_date=BACK, adults=2)
    base.update(kw)
    return SearchRequest(**base)


def test_travelpayouts_parse():
    offers = travelpayouts.parse_offers(TP_PAYLOAD, 2, "USD", {"BA": "British Airways"})
    assert len(offers) == 1
    o = offers[0]
    assert o.price == 824 and o.currency == "USD"
    assert o.outbound.airline == "British Airways" and o.outbound.flight_numbers == ["BA112"]
    assert o.outbound.depart_at == dt.datetime.fromisoformat(f"{DAY}T18:30:00")
    assert o.outbound.duration_minutes == 420 and o.outbound.stops == 0
    assert o.inbound.stops == 1 and o.inbound.origin == "LHR"
    assert o.booking_url == "https://www.aviasales.com/search/NYC1512LON22121?t=abc"


def test_travelpayouts_params():
    p = travelpayouts.TravelpayoutsProvider().build_params(req(max_stops=0, currency="EUR"))
    assert p["departure_at"] == DAY and p["return_at"] == BACK
    assert p["one_way"] == "false" and p["direct"] == "true" and p["currency"] == "eur"


def test_serpapi_parse_and_params():
    offers = serpapi.parse_offers(SERP_PAYLOAD, "USD")
    assert len(offers) == 1
    o = offers[0]
    assert o.price == 655 and o.inbound is None
    assert o.outbound.stops == 1 and o.outbound.via == ["DUB"]
    assert o.outbound.airline_code == "EI" and o.outbound.flight_numbers == ["EI104", "EI168"]
    assert o.booking_url.startswith("https://www.google.com/travel/flights")

    p = serpapi.SerpApiProvider().build_params(
        req(max_stops=1, cabin="business", sort_by="duration", airlines=["ei"], max_price=900)
    )
    assert p["type"] == 1 and p["return_date"] == BACK and p["stops"] == 2
    assert p["travel_class"] == 3 and p["sort_by"] == 5
    assert p["include_airlines"] == "EI" and p["max_price"] == 900


@pytest.fixture()
def fake_http(monkeypatch):
    """Route the providers' HTTP calls to canned responses."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("airlines.json"):
            return httpx.Response(200, json=[{"code": "BA", "name": "British Airways"}])
        if "travelpayouts" in request.url.host:
            return httpx.Response(200, json=TP_PAYLOAD)
        if "serpapi" in request.url.host:
            return httpx.Response(200, json=SERP_PAYLOAD)
        return httpx.Response(404)

    real = httpx.AsyncClient

    def client(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(travelpayouts, "_airline_names", None)
    return seen


def test_search_through_api_with_real_sources(client, monkeypatch, fake_http):
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "tp-test")
    monkeypatch.setenv("SERPAPI_API_KEY", "serp-test")
    providers = {p["name"]: p["available"] for p in client.get("/api/providers").json()}
    assert providers["travelpayouts"] and providers["serpapi"]

    body = {"origin": "JFK", "destination": "LHR", "depart_date": DAY, "return_date": BACK}
    r = client.post("/api/search", json={**body, "provider": "travelpayouts"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["offers"][0]["outbound"]["airline"] == "British Airways"
    assert any("48 hours" in n for n in data["notes"])
    tp_call = next(q for q in fake_http if "prices_for_dates" in q.url.path)
    assert tp_call.headers["X-Access-Token"] == "tp-test"

    r = client.post("/api/search", json={**body, "provider": "serpapi"})
    assert r.status_code == 200, r.text
    assert r.json()["offers"][0]["price"] == 655
    serp_call = next(q for q in fake_http if "serpapi" in q.url.host)
    assert serp_call.url.params["api_key"] == "serp-test"


def test_missing_keys_give_clear_errors(client):
    for name, var in (("travelpayouts", "TRAVELPAYOUTS_TOKEN"), ("serpapi", "SERPAPI_API_KEY")):
        r = client.post("/api/search", json={
            "origin": "JFK", "destination": "LHR", "depart_date": DAY, "provider": name})
        assert r.status_code == 502 and var in r.json()["detail"]


def test_env_file_loading(tmp_path, monkeypatch):
    from app.config import load_env
    f = tmp_path / ".env"
    f.write_text("# comment\nTRAVELPAYOUTS_TOKEN='abc'\nSERPAPI_API_KEY=\n")
    monkeypatch.delenv("TRAVELPAYOUTS_TOKEN", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    load_env(f)
    import os
    assert os.environ["TRAVELPAYOUTS_TOKEN"] == "abc"
    assert "SERPAPI_API_KEY" not in os.environ
