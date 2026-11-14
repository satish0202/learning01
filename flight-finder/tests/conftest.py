import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHT_DB_PATH", str(tmp_path / "test.db"))
    for var in ("DUFFEL_ACCESS_TOKEN", "TRAVELPAYOUTS_TOKEN", "SERPAPI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("app.config.ENV_FILE", tmp_path / "missing.env")
    from app.main import app

    with TestClient(app) as c:
        yield c
