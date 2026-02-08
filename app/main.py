from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import audit, exports, health, intake, jobs, passages, records, reprocess, review, search, tuning
from app.config import get_settings
from app.database import SessionLocal, engine
from app.services.schema import ensure_runtime_schema
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    ensure_runtime_schema(engine)
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    _ = settings.operator_id
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Three Lanterns Internal MVP",
        version="0.1.0",
        description="Milestone 2 backend and curation workflow for Three Lanterns.",
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(health.router)
    app.include_router(intake.router)
    app.include_router(jobs.router)
    app.include_router(passages.router)
    app.include_router(reprocess.router)
    app.include_router(review.router)
    app.include_router(search.router)
    app.include_router(tuning.router)
    app.include_router(exports.router)
    app.include_router(records.router)
    app.include_router(audit.router)
    app.include_router(web_router)

    @app.get("/meta")
    def meta() -> dict:
        settings = get_settings()
        return {
            "service": "three-lanterns-m2",
            "version": "0.1.0",
            "operator_id": settings.operator_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    return app


app = create_app()
