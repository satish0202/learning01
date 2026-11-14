# Flight Finder

A small web app where you type a flight spec (route, dates, passengers, cabin,
max price, max stops, departure time window, airlines) and see matching
flights on the same page. Every search and its results are saved in a local
SQLite database, so you can reopen recent searches from the sidebar.

```
Browser (static/)  ──►  FastAPI middleware (app/)  ──►  Flight source (app/providers/)
   search form             validates spec,                 demo  : offline, made-up data
   results cards           filters & sorts,                duffel: live airline fares API
   recent searches         stores in SQLite (flights.db)
```

## Run it locally

Needs Python 3.9 or newer (the one that comes with macOS works).

```bash
cd flight-finder
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000, enter e.g. `JFK` → `LHR`, pick dates and press
**Find flights**. Results show on the right (below the form on a phone).

Run the tests with `python -m pytest -q`.

## Flight sources

| Source | What it is | Setup |
|---|---|---|
| **Demo data** (default) | Made-up but realistic flights, generated the same way every time for a given spec. Lets you try the full app with no internet or keys. | None |
| **Duffel API** | Real airline offers from [Duffel](https://duffel.com/docs/api/offer-requests). A free test token returns Duffel's sandbox airline; a live token returns real fares. | Sign up at duffel.com, create an access token, then `export DUFFEL_ACCESS_TOKEN=duffel_test_...` before starting the server. |

**Why an API rather than scraping sites?** Google Flights, Skyscanner,
Kayak and airline sites forbid automated scraping in their terms and actively
block bots, so a scraper would be fragile and against their rules. Duffel is
built for programmatic access. (Amadeus' free self-service API, the other
common choice, was shut down in 2026.) New sources can be added by writing a
class in `app/providers/` that implements `FlightProvider.search()` and
registering it in `app/providers/__init__.py`; filtering, sorting and storage
are shared.

Limitations of this first version:
- Duffel prices come back in the airline's currency; the max-price filter is
  compared in that currency (the page tells you when this happens).
- Departure times are local airport times.
- Booking is not supported; results are for finding flights only.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/search` | Run a search. Body is the flight spec (see `app/models.py::SearchRequest`). |
| `GET` | `/api/searches` | Recent searches with result count and cheapest price. |
| `GET` | `/api/searches/{id}` | A saved search with its flights. |
| `DELETE` | `/api/searches/{id}` | Delete a saved search. |
| `GET` | `/api/providers` | Available flight sources. |

Interactive docs: http://localhost:8000/docs

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FLIGHT_DB_PATH` | `flights.db` | SQLite file for searches and results |
| `DUFFEL_ACCESS_TOKEN` | (empty) | Enables the Duffel source |

## Project layout

```
flight-finder/
  app/
    main.py          FastAPI routes, serves the page
    models.py        Flight spec and result models (validation lives here)
    search.py        Filters, sorting, saving results
    db.py            SQLite schema and queries
    providers/       demo.py, duffel.py, base.py
  static/            index.html, app.js, styles.css (no build step)
  tests/             API and parser tests
```
