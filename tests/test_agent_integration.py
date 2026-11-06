import asyncio
import socket

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db.engine import close_db, get_session_factory, init_db
from app.db.models import Memory, Target
from app.db.models import TestResult as DbTestResult
from app.db.models import TestRun as DbTestRun
from app.db.seed import seed_test_cases
from app.services.memory import close_memory, read_short_term
from app.services.test_runner import run_stream

pytestmark = pytest.mark.integration


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


async def _run_real_evaluation() -> dict:
    settings = get_settings()
    assert settings.database_url
    assert settings.redis_url
    assert settings.model_api_key
    assert settings.embedding_api_key

    await init_db()
    await seed_test_cases()
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            target = (
                await session.execute(
                    select(Target)
                    .where(
                        Target.authorized.is_(True),
                        Target.endpoint.like("mock://%"),
                    )
                    .order_by(Target.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if target is None:
                target = Target(
                    name="Agent integration mock",
                    endpoint="mock://secure",
                    model="mock-model",
                    authorized=True,
                    allowed_categories=[
                        "prompt_boundary",
                        "data_protection",
                        "tool_boundary",
                    ],
                )
                session.add(target)
                await session.commit()
                await session.refresh(target)

            memory_before = (
                await session.execute(
                    select(func.count())
                    .select_from(Memory)
                    .where(Memory.target_id == target.id)
                )
            ).scalar_one()
            run = DbTestRun(target_id=target.id, status="pending")
            session.add(run)
            await session.commit()
            await session.refresh(run)

            chunks = [
                chunk
                async for chunk in run_stream(run.id, ["prompt_boundary"])
            ]

            await session.refresh(run)
            result_count = (
                await session.execute(
                    select(func.count())
                    .select_from(DbTestResult)
                    .where(DbTestResult.run_id == run.id)
                )
            ).scalar_one()
            memory_after = (
                await session.execute(
                    select(func.count())
                    .select_from(Memory)
                    .where(Memory.target_id == target.id)
                )
            ).scalar_one()
            short_term = await read_short_term(run.id)
            return {
                "run_id": run.id,
                "status": run.status,
                "summary": run.summary,
                "result_count": result_count,
                "memory_before": memory_before,
                "memory_after": memory_after,
                "short_term_events": [item.get("event") for item in short_term],
                "stream": "".join(chunks),
            }
    finally:
        await close_memory()
        await close_db()


def test_real_agent_run_persists_results_and_memory():
    settings = get_settings()
    if not settings.database_url or not settings.model_api_key or not settings.embedding_api_key:
        pytest.skip("real model/database settings are not configured")
    if not _port_open(15432) or not _port_open(16379):
        pytest.skip("PostgreSQL or Redis tunnel is not listening")

    outcome = asyncio.run(_run_real_evaluation())

    assert outcome["status"] in {"completed", "completed_with_errors"}
    assert outcome["result_count"] == 2
    assert outcome["memory_after"] == outcome["memory_before"] + 1
    assert outcome["summary"]["agent"]["iterations"] == 2
    assert "event: case_planned" in outcome["stream"]
    assert "event: case_started" in outcome["stream"]
    assert "event: case_result" in outcome["stream"]
    assert "event: run_completed" in outcome["stream"]
    assert "run_started" in outcome["short_term_events"]
    assert "case_result" in outcome["short_term_events"]
