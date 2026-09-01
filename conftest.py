"""
Shared pytest fixtures for the fastapi-telemetry test suite.

Each test gets a fresh in-memory SQLite database, so:
  - main.py's `lifespan` seed data is never inserted (lifespan only runs
    against the real DATABASE_URL engine, which these tests never touch)
  - tests never depend on execution order or leftover rows from prior runs
"""
import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool
from fastapi.testclient import TestClient
from main import app, get_session


@pytest.fixture(name="session")
def session_fixture():
    # StaticPool + check_same_thread=False: keeps the single in-memory
    # SQLite DB alive across the app's and the test's separate connections
    # for the duration of one test.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
