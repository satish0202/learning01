"""Local SQLite storage for searches and the flights they found."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from .models import FlightOffer, SearchRequest, SearchSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    origin        TEXT    NOT NULL,
    destination   TEXT    NOT NULL,
    depart_date   TEXT    NOT NULL,
    return_date   TEXT,
    adults        INTEGER NOT NULL,
    provider      TEXT    NOT NULL,
    currency      TEXT    NOT NULL,
    request_json  TEXT    NOT NULL,
    result_count  INTEGER NOT NULL DEFAULT 0,
    total_found   INTEGER NOT NULL DEFAULT 0,
    cheapest_price REAL,
    notes_json    TEXT    NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS flights (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id        INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    rank             INTEGER NOT NULL,
    provider         TEXT    NOT NULL,
    airline          TEXT    NOT NULL,
    price            REAL    NOT NULL,
    currency         TEXT    NOT NULL,
    depart_at        TEXT    NOT NULL,
    arrive_at        TEXT    NOT NULL,
    stops            INTEGER NOT NULL,
    duration_minutes INTEGER NOT NULL,
    offer_json       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flights_search ON flights(search_id, rank);
"""


def db_path() -> str:
    return os.environ.get("FLIGHT_DB_PATH", "flights.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_search(
    req: SearchRequest, offers: list[FlightOffer], notes: list[str], total_found: int
) -> tuple[int, dt.datetime]:
    created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    cheapest = min((o.price for o in offers), default=None)
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO searches (created_at, origin, destination, depart_date,
                   return_date, adults, provider, currency, request_json,
                   result_count, total_found, cheapest_price, notes_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                created.isoformat(),
                req.origin,
                req.destination,
                req.depart_date.isoformat(),
                req.return_date.isoformat() if req.return_date else None,
                req.adults,
                req.provider,
                req.currency,
                req.model_dump_json(),
                len(offers),
                total_found,
                cheapest,
                json.dumps(notes),
            ),
        )
        search_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO flights (search_id, rank, provider, airline, price, currency,
                   depart_at, arrive_at, stops, duration_minutes, offer_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    search_id,
                    i,
                    o.provider,
                    o.outbound.airline,
                    o.price,
                    o.currency,
                    o.outbound.depart_at.isoformat(),
                    o.outbound.arrive_at.isoformat(),
                    o.max_stops,
                    o.total_minutes,
                    o.model_dump_json(),
                )
                for i, o in enumerate(offers)
            ],
        )
    return search_id, created


def list_searches(limit: int = 20) -> list[SearchSummary]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM searches ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        SearchSummary(
            id=r["id"],
            created_at=r["created_at"],
            origin=r["origin"],
            destination=r["destination"],
            depart_date=r["depart_date"],
            return_date=r["return_date"],
            adults=r["adults"],
            provider=r["provider"],
            result_count=r["result_count"],
            cheapest_price=r["cheapest_price"],
            currency=r["currency"],
        )
        for r in rows
    ]


def get_search(
    search_id: int,
) -> Optional[tuple[dt.datetime, SearchRequest, list[FlightOffer], list[str], int]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
        if row is None:
            return None
        flights = conn.execute(
            "SELECT offer_json FROM flights WHERE search_id = ? ORDER BY rank",
            (search_id,),
        ).fetchall()
    req = SearchRequest.model_validate_json(row["request_json"])
    offers = [FlightOffer.model_validate_json(f["offer_json"]) for f in flights]
    created = dt.datetime.fromisoformat(row["created_at"])
    return created, req, offers, json.loads(row["notes_json"]), row["total_found"]


def delete_search(search_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM searches WHERE id = ?", (search_id,))
    return cur.rowcount > 0
