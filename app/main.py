from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, knowledge, mock_target, runs, targets, test_cases
from app.config import get_settings
from app.db.engine import close_db, init_db
from app.db.seed import seed_test_cases
from app.services.memory import close_memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        if settings.database_url:
            await init_db()
            await seed_test_cases()
        yield
    finally:
        try:
            await close_memory()
        finally:
            await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(targets.router)
    app.include_router(test_cases.router)
    app.include_router(runs.router)
    app.include_router(mock_target.router)
    app.include_router(knowledge.router)
    return app


app = create_app()

