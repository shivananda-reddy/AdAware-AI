import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_analyze_hover_requires_content():
    response = client.post("/analyze_hover", json={})
    assert response.status_code == 400
    body = response.json()
    assert body.get("detail")
    assert "image" in body["detail"].lower() or "caption" in body["detail"].lower()
