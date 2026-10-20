"""
tests/test_api.py — FastAPI endpoint smoke tests.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


# Patch DB dependency so tests run without a live database
@pytest.fixture
def client():
    from api.main import app
    with patch("api.db.engine"), patch("api.db.SessionLocal"):
        with TestClient(app) as c:
            yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "EV Infra" in resp.json()["message"]


def test_docs_reachable(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
