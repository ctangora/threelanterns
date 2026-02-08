import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test_m2.db")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPERATOR_ID", "test-operator")
os.environ.setdefault("USE_MOCK_AI", "true")
os.environ.setdefault("OPENAI_MODEL", "gpt-5")
os.environ.setdefault("INGEST_ROOT", str(Path(__file__).resolve().parents[1] / "__Reference__"))

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.base import Base  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db():
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    with SessionLocal() as db:
        yield db
        db.rollback()

