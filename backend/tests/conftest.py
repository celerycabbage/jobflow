import os
import shutil
from pathlib import Path

TEST_DATABASE = Path(__file__).parent / "test.db"
TEST_UPLOADS = Path(__file__).parent / "uploads"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes"
os.environ["UPLOAD_DIR"] = str(TEST_UPLOADS)

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)
    shutil.rmtree(TEST_UPLOADS, ignore_errors=True)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register", json={"email": "owner@example.com", "password": "password123"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
