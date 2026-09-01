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
    assert response.json() == {"status": "ok"}


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
