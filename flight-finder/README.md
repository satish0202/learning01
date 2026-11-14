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

| Source | Prices | Cost | Setup |
|---|---|---|---|
| **Aviasales prices** (Travelpayouts Data API) | Real fares that Aviasales users found in the last 48 hours. A cache, not a live search, so check the price on the booking page. Economy only. | Free, no monthly cap | Sign up at [travelpayouts.com](https://www.travelpayouts.com), copy the token from Profile → API token, put it in `.env` as `TRAVELPAYOUTS_TOKEN`. |
| **Google Flights live** (SerpApi) | Live Google Flights results. For round trips it shows the outbound flight with the round-trip total; pick the return on Google Flights with the Book link. | Free plan: 250 searches a month, 50 an hour. Each search uses one. | Sign up at [serpapi.com](https://serpapi.com), copy the key from your dashboard, put it in `.env` as `SERPAPI_API_KEY`. |
| **Demo data** | Made-up flights, so the app works with no keys. | Free | None |
| **Duffel API** | Test mode returns Duffel's sandbox airline only; real fares need a verified paid account. | Paid for real fares | `DUFFEL_ACCESS_TOKEN` |

To add your keys:

```bash
cp .env.example .env     # then edit .env and paste your token/key
uvicorn app.main:app --reload
```

The source picker on the page shows which sources are set up. The first real
source with a key is selected by default.

**Why APIs rather than scraping sites?** Google Flights, Skyscanner, Kayak and
airline sites forbid automated scraping in their terms and actively block
bots, so a scraper of our own would be fragile and against their rules.
Travelpayouts allows token holders to use its Data API without restrictions.
SerpApi does the Google Flights collection on its side; note that Google is
suing SerpApi over this (filed December 2025, still open), and the free plan
doesn't include SerpApi's legal cover. Kiwi Tequila closed to new developers in
2024 and Amadeus' free API shut down in 2026.

New sources can be added by writing a class in `app/providers/` that
implements `FlightProvider.search()` and registering it in
`app/providers/__init__.py`; filtering, sorting and storage are shared.

Limitations:
- Aviasales arrival times are estimated from the flight duration, in the
  departure airport's local time. Its per-person fares are multiplied by the
  number of adults.
- Some routes or dates have no Aviasales data, especially quiet routes or
  dates far ahead. Try the SerpApi source for those.
- Departure times are local airport times.
- Booking happens on the source's site via the Book link.

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
| `TRAVELPAYOUTS_TOKEN` | (empty) | Enables Aviasales prices |
| `SERPAPI_API_KEY` | (empty) | Enables Google Flights live |
| `DUFFEL_ACCESS_TOKEN` | (empty) | Enables the Duffel source |

Set them in a `.env` file in `flight-finder/` (see `.env.example`) or export
them in your shell.

## Project layout

```
flight-finder/
  app/
    main.py          FastAPI routes, serves the page
    models.py        Flight spec and result models (validation lives here)
    search.py        Filters, sorting, saving results
    db.py            SQLite schema and queries
    config.py        Reads settings from .env
    providers/       travelpayouts.py, serpapi.py, demo.py, duffel.py, base.py
  static/            index.html, app.js, styles.css (no build step)
  tests/             API and parser tests
```
