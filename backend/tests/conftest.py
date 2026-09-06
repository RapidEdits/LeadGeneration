"""Pytest fixtures. DB-backed tests run against the configured PostgreSQL.

If Postgres is unreachable, DB-backed tests are skipped (pure-function tests
still run). Inside docker-compose (`backend` container) Postgres is available,
so these run fully. Set POSTGRES_DB=leadgen_test to isolate from dev data.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("ENCRYPTION_KEY", "H1a3p7Qp9m2v6Yw8Zx0Nc4Rb5Td6Uf7Gk8Lm9Pq0Rs4=")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: F401,E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


# Tests run against a DEDICATED database so they never clobber dev data.
# Derived by appending _test to the configured DB name.
TEST_DB = f"{settings.POSTGRES_DB}_test"
_TEST_URI = settings.sqlalchemy_database_uri.rsplit("/", 1)[0] + f"/{TEST_DB}"


def _ensure_test_db() -> bool:
    """Create the <db>_test database if the server is reachable. Returns availability."""
    try:
        admin = create_engine(settings.sqlalchemy_database_uri, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            exists = c.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
            ).first()
            if not exists:
                c.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
        admin.dispose()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _ensure_test_db(), reason="PostgreSQL not reachable")


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(_TEST_URI)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def client(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Clean tables between tests for isolation.
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'DELETE FROM "{table.name}"'))
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def db(engine):
    """A DB session bound to the test engine (for exercising services directly)."""
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = TestingSession()
    try:
        yield s
    finally:
        s.close()


def signup(client, email="owner@example.com", ws="Acme"):
    resp = client.post("/api/v1/auth/signup", json={
        "email": email, "password": "supersecret123", "full_name": "Owner", "workspace_name": ws,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["access_token"], data["workspace"]["id"]


def auth_headers(token, ws_id):
    return {"Authorization": f"Bearer {token}", "X-Workspace-Id": ws_id}
