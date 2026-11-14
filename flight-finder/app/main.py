"""FastAPI app: serves the search page and the JSON API behind it."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .models import SearchRequest, SearchResult, SearchSummary
from .providers import ProviderError, list_providers
from .search import run_search

STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Flight Finder", version="0.1.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/providers")
def providers() -> list[dict]:
    return list_providers()


@app.post("/api/search", response_model=SearchResult)
async def search(req: SearchRequest) -> SearchResult:
    try:
        return await run_search(req)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.get("/api/searches", response_model=list[SearchSummary])
def searches(limit: int = 20) -> list[SearchSummary]:
    return db.list_searches(min(max(limit, 1), 100))


@app.get("/api/searches/{search_id}", response_model=SearchResult)
def get_search(search_id: int) -> SearchResult:
    found = db.get_search(search_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Search not found")
    created, req, offers, notes, total_found = found
    return SearchResult(
        search_id=search_id,
        created_at=created,
        request=req,
        offers=offers,
        total_found=total_found,
        notes=notes,
    )


@app.delete("/api/searches/{search_id}", status_code=204)
def delete_search(search_id: int) -> None:
    if not db.delete_search(search_id):
        raise HTTPException(status_code=404, detail="Search not found")
