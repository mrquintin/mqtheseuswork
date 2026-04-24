import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "RESEARCHER_API_KEYS",
    "tester:sandbox-test:sk-test-key-0000000000000001",
)

from researcher_api.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_healthz_no_auth(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200


def test_security_policy_public(client: TestClient) -> None:
    r = client.get("/security")
    assert r.status_code == 200
    assert "Coordinated disclosure" in r.text


def test_extract_requires_key(client: TestClient) -> None:
    r = client.post("/v1/extract-claims", json={"text": "hello"})
    assert r.status_code == 401


def test_predict_score_with_key(client: TestClient) -> None:
    r = client.post(
        "/v1/predict-score",
        headers={"X-API-Key": "sk-test-key-0000000000000001"},
        json={
            "predictions": [
                {"prob_low": 0.7, "prob_high": 0.9, "outcome": 1},
                {"prob_low": 0.7, "prob_high": 0.9, "outcome": 0},
            ]
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["metrics"]["n"] == 2
    assert "X-Theseus-API-Version" in r.headers
