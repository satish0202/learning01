import datetime as dt

from app.providers.duffel import DuffelProvider, parse_duration, parse_offers
from app.models import SearchRequest


def future(days):
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def spec(**kw):
    base = {
        "origin": "jfk",
        "destination": "LHR",
        "depart_date": future(20),
        "return_date": future(27),
        "adults": 2,
        "provider": "demo",
    }
    base.update(kw)
    return base


def test_page_and_providers(client):
    assert client.get("/").status_code == 200
    names = {p["name"]: p for p in client.get("/api/providers").json()}
    assert names["demo"]["available"] is True
    assert names["duffel"]["available"] is False


def test_search_applies_filters_and_is_saved(client):
    r = client.post("/api/search", json=spec(max_price=2500, max_stops=1, sort_by="price"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["request"]["origin"] == "JFK"
    offers = body["offers"]
    assert offers, "demo source should return matches"
    prices = [o["price"] for o in offers]
    assert prices == sorted(prices)
    assert all(p <= 2500 for p in prices)
    for o in offers:
        assert o["outbound"]["stops"] <= 1 and o["inbound"]["stops"] <= 1

    history = client.get("/api/searches").json()
    assert history[0]["id"] == body["search_id"]
    again = client.get(f"/api/searches/{body['search_id']}").json()
    assert again["offers"] == offers
    assert again["total_found"] == body["total_found"]


def test_departure_window_and_airline_filter(client):
    r = client.post(
        "/api/search",
        json=spec(return_date=None, earliest_departure="08:00", latest_departure="14:00", airlines=["BA", "AA"]),
    )
    assert r.status_code == 200
    for o in r.json()["offers"]:
        assert "08:00" <= o["outbound"]["depart_at"][11:16] <= "14:00"
        assert o["outbound"]["airline_code"] in {"BA", "AA"}
        assert o["inbound"] is None


def test_validation_errors(client):
    assert client.post("/api/search", json=spec(origin="NEWYORK")).status_code == 422
    assert client.post("/api/search", json=spec(destination="JFK")).status_code == 422
    assert client.post("/api/search", json=spec(depart_date=future(-1), return_date=None)).status_code == 422
    assert client.post("/api/search", json=spec(return_date=future(1))).status_code == 422


def test_duffel_without_token_is_clear_error(client):
    r = client.post("/api/search", json=spec(provider="duffel"))
    assert r.status_code == 502
    assert "DUFFEL_ACCESS_TOKEN" in r.json()["detail"]


def test_delete_search(client):
    sid = client.post("/api/search", json=spec()).json()["search_id"]
    assert client.delete(f"/api/searches/{sid}").status_code == 204
    assert client.get(f"/api/searches/{sid}").status_code == 404


def test_parse_duration():
    assert parse_duration("PT7H35M") == 455
    assert parse_duration("P1DT2H") == 1560
    assert parse_duration(None) is None


def test_duffel_body_and_parsing():
    req = SearchRequest(**spec(max_stops=0))
    body = DuffelProvider().build_body(req)["data"]
    assert len(body["slices"]) == 2 and len(body["passengers"]) == 2
    assert body["max_connections"] == 0

    seg = lambda o, d, a, b, n: {
        "origin": {"iata_code": o}, "destination": {"iata_code": d},
        "departing_at": a, "arriving_at": b,
        "marketing_carrier": {"iata_code": "ZZ", "name": "Duffel Airways"},
        "marketing_carrier_flight_number": n,
    }
    payload = {"data": {"offers": [{
        "total_amount": "812.40", "total_currency": "GBP",
        "owner": {"iata_code": "ZZ", "name": "Duffel Airways"},
        "slices": [
            {"origin": {"iata_code": "JFK"}, "destination": {"iata_code": "LHR"}, "duration": "PT9H",
             "segments": [seg("JFK", "DUB", "2030-01-01T08:00:00", "2030-01-01T14:00:00", "1"),
                          seg("DUB", "LHR", "2030-01-01T15:00:00", "2030-01-01T17:00:00", "2")]},
            {"origin": {"iata_code": "LHR"}, "destination": {"iata_code": "JFK"}, "duration": "PT8H",
             "segments": [seg("LHR", "JFK", "2030-01-08T10:00:00", "2030-01-08T18:00:00", "3")]},
        ],
    }, {"broken": True}]}}
    offers = parse_offers(payload)
    assert len(offers) == 1
    o = offers[0]
    assert o.price == 812.40 and o.currency == "GBP"
    assert o.outbound.stops == 1 and o.outbound.via == ["DUB"]
    assert o.outbound.flight_numbers == ["ZZ1", "ZZ2"]
    assert o.inbound.duration_minutes == 480
