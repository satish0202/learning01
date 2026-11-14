import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("DUFFEL_ACCESS_TOKEN", raising=False)
    from app.main import app

    with TestClient(app) as c:
        yield c
