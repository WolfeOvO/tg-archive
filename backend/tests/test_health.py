from api.health import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_health_endpoint_is_public_and_reports_ok():
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
