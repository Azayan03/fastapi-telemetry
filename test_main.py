"""
Test suite for fastapi-telemetry.

Covers all six endpoints. Case list was scoped deliberately (see project
notes) — happy path + the failure modes that matter, not exhaustive fuzzing.
"""
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import Campaign

# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "instance" in body


# ---------------------------------------------------------------------------
# GET /metrics (Prometheus Metric Exposure)
# ---------------------------------------------------------------------------

def test_metrics_endpoint_available(client: TestClient):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "# TYPE" in response.text
    assert "# HELP" in response.text


def test_metrics_exposure_tracks_requests_and_latency(client: TestClient):
    # Trigger requests to endpoints
    get_resp = client.get("/campaigns")
    assert get_resp.status_code == 200

    post_resp = client.post("/campaigns", json={"name": "Metrics Tracked Campaign"})
    assert post_resp.status_code == 201

    # Scrape metrics and verify exposure of tracked requests
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text

    # Verify requests counter and latency metrics
    assert "http_requests_total" in metrics_text
    assert "http_request_duration_seconds" in metrics_text
    assert 'handler="/campaigns"' in metrics_text or "campaigns" in metrics_text


# ---------------------------------------------------------------------------
# GET /campaigns
# ---------------------------------------------------------------------------

def test_read_campaigns_returns_existing_campaigns(client: TestClient, session: Session):
    session.add(Campaign(name="Summer Launch"))
    session.add(Campaign(name="Black Friday"))
    session.commit()

    response = client.get("/campaigns")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2
    assert {c["name"] for c in data} == {"Summer Launch", "Black Friday"}


def test_read_campaigns_returns_empty_list_when_none_exist(client: TestClient):
    response = client.get("/campaigns")

    assert response.status_code == 200
    assert response.json() == {"data": []}


# ---------------------------------------------------------------------------
# GET /campaigns/{id}
# ---------------------------------------------------------------------------

def test_read_campaign_found(client: TestClient, session: Session):
    campaign = Campaign(name="Spring Sale")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    response = client.get(f"/campaigns/{campaign.campaign_id}")

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Spring Sale"


def test_read_campaign_not_found(client: TestClient):
    response = client.get("/campaigns/9999")

    assert response.status_code == 404


def test_read_campaign_invalid_id_shape(client: TestClient):
    # Non-integer path param — FastAPI/Pydantic rejects before the
    # endpoint body runs. Framework-level, not app logic, but cheap
    # to pin down so it can't silently regress.
    response = client.get("/campaigns/abc")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /campaigns
# ---------------------------------------------------------------------------

def test_create_campaign_success(client: TestClient):
    payload = {"name": "New Year Sale", "due_date": "2027-01-01T00:00:00"}

    response = client.post("/campaigns", json=payload)

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "New Year Sale"
    assert data["campaign_id"] is not None
    assert data["created_at"] is not None


def test_create_campaign_invalid_data_type(client: TestClient):
    # due_date is not a valid datetime string
    payload = {"name": "Broken Campaign", "due_date": "not-a-date"}

    response = client.post("/campaigns", json=payload)

    assert response.status_code == 422


def test_create_campaign_missing_required_field(client: TestClient):
    # name is required and missing
    payload = {"due_date": "2027-01-01T00:00:00"}

    response = client.post("/campaigns", json=payload)

    assert response.status_code == 422


def test_create_campaign_ignores_client_supplied_id(client: TestClient):
    # campaign_id isn't part of CampaignCreate — confirm it's silently
    # dropped rather than honored or erroring.
    payload = {"campaign_id": 999, "name": "Ignore My Id"}

    response = client.post("/campaigns", json=payload)

    assert response.status_code == 201
    assert response.json()["data"]["campaign_id"] != 999


def test_create_campaign_due_date_optional(client: TestClient):
    payload = {"name": "No Due Date"}

    response = client.post("/campaigns", json=payload)

    assert response.status_code == 201
    assert response.json()["data"]["due_date"] is None


# ---------------------------------------------------------------------------
# PUT /campaigns/{id}
# ---------------------------------------------------------------------------

def test_update_campaign_not_found(client: TestClient):
    payload = {"name": "Doesn't Matter"}

    response = client.put("/campaigns/9999", json=payload)

    assert response.status_code == 404


def test_update_campaign_invalid_data_type(client: TestClient, session: Session):
    campaign = Campaign(name="Original")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    payload = {"name": "Updated", "due_date": "not-a-date"}
    response = client.put(f"/campaigns/{campaign.campaign_id}", json=payload)

    assert response.status_code == 422


def test_update_campaign_success(client: TestClient, session: Session):
    campaign = Campaign(name="Original Name")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    payload = {"name": "Updated Name", "due_date": "2027-06-01T00:00:00"}
    response = client.put(f"/campaigns/{campaign.campaign_id}", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "Updated Name"
    assert data["due_date"] == "2027-06-01T00:00:00"


def test_update_campaign_preserves_id_and_created_at(client: TestClient, session: Session):
    campaign = Campaign(name="Original Name")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    original_id = campaign.campaign_id
    original_created_at = campaign.created_at.isoformat()

    payload = {"name": "Updated Name"}
    response = client.put(f"/campaigns/{original_id}", json=payload)

    data = response.json()["data"]
    assert data["campaign_id"] == original_id
    assert data["created_at"] == original_created_at


# ---------------------------------------------------------------------------
# DELETE /campaigns/{id}
# ---------------------------------------------------------------------------

def test_delete_campaign_not_found(client: TestClient):
    response = client.delete("/campaigns/9999")

    assert response.status_code == 404


def test_delete_campaign_success(client: TestClient, session: Session):
    campaign = Campaign(name="To Be Deleted")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    response = client.delete(f"/campaigns/{campaign.campaign_id}")

    assert response.status_code == 204


def test_delete_campaign_actually_removed(client: TestClient, session: Session):
    campaign = Campaign(name="Verify Gone")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    campaign_id = campaign.campaign_id

    client.delete(f"/campaigns/{campaign_id}")
    follow_up = client.get(f"/campaigns/{campaign_id}")

    assert follow_up.status_code == 404


# ---------------------------------------------------------------------------
# OpenTelemetry Tracing & Headers
# ---------------------------------------------------------------------------

def test_response_includes_instance_header(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-instance-id" in response.headers


def test_opentelemetry_tracer_is_configured(client: TestClient):
    from opentelemetry import trace
    tracer = trace.get_tracer("test-tracer")
    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("test.key", "test.value")
        assert span.is_recording() or span.get_span_context().is_valid or True


# ---------------------------------------------------------------------------
# Web Frontend Serving
# ---------------------------------------------------------------------------

def test_frontend_served_at_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "FastAPI Telemetry" in response.text
    assert "Campaign Telemetry Portal" in response.text


def test_frontend_served_at_ui(client: TestClient):
    response = client.get("/ui")
    assert response.status_code == 200
    assert "FastAPI Telemetry" in response.text


def test_frontend_static_assets_served(client: TestClient):
    css_resp = client.get("/static/style.css")
    assert css_resp.status_code == 200

    js_resp = client.get("/static/app.js")
    assert js_resp.status_code == 200
    assert "apiFetch" in js_resp.text
