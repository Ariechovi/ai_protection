import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db.engine import get_session_factory
from app.db.models import Target, TestCase, TestRun
from app.services.evaluation_agent import EvaluationAgent
from app.services.memory import (
    append_short_term,
    remember_target_profile,
)
from app.services.redaction import redact_text

logger = logging.getLogger(__name__)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_stream(run_id: str, categories: list[str] | None = None) -> AsyncIterator[str]:
    session_factory = get_session_factory()
    settings = get_settings()
    async with session_factory() as session:
        run = await session.get(TestRun, run_id)
        if run is None:
            yield sse("error", {"message": "run not found"})
            return
        target = await session.get(Target, run.target_id)
        if target is None:
            yield sse("error", {"message": "target not found"})
            return

        allowed_categories = set(target.allowed_categories or [])
        selected_categories = (
            set(categories) & allowed_categories
            if categories is not None and allowed_categories
            else set(categories or allowed_categories)
        )

        query = select(TestCase).where(TestCase.enabled.is_(True))
        if allowed_categories or categories is not None:
            query = query.where(TestCase.category.in_(selected_categories))
        result = await session.execute(
            query.order_by(TestCase.id).limit(settings.max_test_cases)
        )
        cases = list(result.scalars().all())
        run.status = "running"
        await session.commit()
        run_started = {
            "run_id": run.id,
            "target": target.name,
            "count": len(cases),
            "categories": sorted(selected_categories),
            "agent_mode": settings.agent_runtime_mode,
        }
        await append_short_term(run.id, {"event": "run_started", **run_started})
        yield sse("run_started", run_started)

        final_state: dict = {}
        agent = EvaluationAgent(
            target=target,
            cases=cases,
            run_id=run.id,
            session=session,
            settings=settings,
            categories=sorted(selected_categories),
        )
        try:
            async for item in agent.stream():
                event = item.get("event", "message")
                if event == "_completed_state":
                    final_state = item.get("data", {})
                    continue
                payload = {key: value for key, value in item.items() if key != "event"}
                await append_short_term(run.id, item)
                yield sse(event, payload)
        except Exception as exc:
            logger.exception("Evaluation agent failed")
            message = f"{type(exc).__name__}: {redact_text(str(exc))}"[:1000]
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.summary = {"error": message, "text": "评测 Agent 执行失败。"}
            await session.commit()
            error_event = {"message": message}
            await append_short_term(run.id, {"event": "error", **error_event})
            yield sse("error", error_event)
            return

        summary = final_state.get("summary")
        if not summary:
            raise RuntimeError("evaluation agent finished without a summary")
        errors = int(summary.get("errors", 0))
        run.status = "completed_with_errors" if errors else "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.summary = summary
        await session.commit()
        try:
            await asyncio.wait_for(
                remember_target_profile(
                    target,
                    run.id,
                    run.summary,
                    final_state.get("result_rows", []),
                ),
                timeout=settings.memory_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("Long-term memory write degraded: %s", type(exc).__name__)
        run_completed = {"run_id": run.id, "summary": run.summary}
        await append_short_term(run.id, {"event": "run_completed", **run_completed})
        yield sse("run_completed", run_completed)

