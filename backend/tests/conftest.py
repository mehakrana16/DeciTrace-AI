"""Pytest configuration.

A throwaway SQLite database is created per test session in a temp directory so
the tests never touch the developer's own ``data/decitrace.db``.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# --- must be set BEFORE the app package is imported -------------------------
_TMP = Path(tempfile.mkdtemp(prefix="decitrace-test-"))
os.environ["DECITRACE_DATA_DIR"] = str(_TMP)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["LLM_PROVIDER"] = "none"  # deterministic mode in CI
os.environ["VECTOR_BACKEND"] = "auto"
os.environ["EMBEDDING_BACKEND"] = "auto"


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    """Create the schema and seed the synthetic world exactly once."""
    from app.data.db import init_db
    from app.data.seed import seed_database

    init_db()
    seed_database(total_customers=18, reset=True)
    yield


@pytest.fixture(scope="session")
def seeded_app(prepared_database):
    """Return a FastAPI TestClient bound to the seeded test database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def sample_customer_id(seeded_app):
    response = seeded_app.get("/api/customers?limit=1")
    assert response.status_code == 200
    rows = response.json()
    assert rows, "seed produced no customers"
    return rows[0]["customer_id"]
