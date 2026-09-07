"""
Phase 1 smoke tests — these deliberately avoid needing a live database or a
real Anthropic API key, so `pytest` can confirm the app wires together
correctly before you've configured anything.

Run with: pytest backend/tests/test_health.py -v
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Solution AI"
    assert body["status"] == "running"


def test_openapi_schema_generates():
    """If this fails, a route is misconfigured somewhere."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
