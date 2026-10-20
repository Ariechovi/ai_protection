import json
from pathlib import Path

from sqlalchemy import func, select

from app.db.engine import get_session_factory
from app.db.models import TestCase

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "test_cases.json"


async def seed_test_cases() -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(TestCase))
        if count:
            return
        rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        session.add_all([TestCase(**row) for row in rows])
        await session.commit()

