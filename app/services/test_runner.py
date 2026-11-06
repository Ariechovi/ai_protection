import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db.engine import get_session_factory
from app.db.models import Target, TestCase, TestResult, TestRun
from app.services.judge import JudgeResult, judge_case
from app.services.memory import (
    MemoryContext,
    append_short_term,
    build_summary_text,
    load_context,
    remember_target_profile,
)
from app.services.redaction import redact_text
from app.services.target_adapter import TargetAdapter

logger = logging.getLogger(__name__)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def execute_case(
    adapter: TargetAdapter,
    case: TestCase,
    settings,
    memory_text: str = "",
):
    """Execute one case with target/judge timeouts and a safe fallback result."""
    transcript = None
    try:
        transcript = await asyncio.wait_for(
            adapter.run_steps(case.steps),
            timeout=settings.target_timeout_seconds,
        )
    except Exception as exc:
        message = redact_text(f"target error: {type(exc).__name__}")[:500]
        return (
            None,
            JudgeResult(
                verdict="UNKNOWN",
                severity=case.severity,
                confidence=0.0,
                reason=message,
            ),
            message,
        )

    try:
        judgement = await asyncio.wait_for(
            judge_case(case, transcript, memory_text=memory_text),
            timeout=settings.judge_timeout_seconds,
        )
        return transcript, judgement, None
    except Exception as exc:
        message = redact_text(f"judge error: {type(exc).__name__}")[:500]
        return (
            transcript,
            JudgeResult(
                verdict="UNKNOWN",
                severity=case.severity,
                confidence=0.0,
                reason=message,
            ),
            message,
        )


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

        query = select(TestCase).where(TestCase.enabled.is_(True))
        if categories:
            query = query.where(TestCase.category.in_(categories))
        result = await session.execute(
            query.order_by(TestCase.id).limit(settings.max_test_cases)
        )
        cases = list(result.scalars().all())
        run.status = "running"
        await session.commit()
        run_started = {"run_id": run.id, "target": target.name, "count": len(cases)}
        await append_short_term(run.id, {"event": "run_started", **run_started})
        yield sse("run_started", run_started)

        counts = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0}
        errors = 0
        result_rows: list[dict] = []
        covered_categories = sorted({case.category for case in cases})
        adapter = TargetAdapter(target)
        for case in cases:
            case_started = {"case_id": case.id, "name": case.name}
            await append_short_term(run.id, {"event": "case_started", **case_started})
            yield sse("case_started", case_started)
            try:
                memory = await asyncio.wait_for(
                    load_context(
                        target.id,
                        run.id,
                        f"{case.name} {case.description}",
                    ),
                    timeout=settings.memory_timeout_seconds,
                )
            except Exception as exc:
                logger.warning("Memory context load degraded: %s", type(exc).__name__)
                memory = MemoryContext()
            memory_text = memory.render()
            transcript, judgement, error_message = await execute_case(
                adapter,
                case,
                settings,
                memory_text=memory_text,
            )
            if error_message:
                errors += 1
                error_event = {"case_id": case.id, "message": error_message}
                await append_short_term(run.id, {"event": "error", **error_event})
                yield sse("error", error_event)

            counts[judgement.verdict] = counts.get(judgement.verdict, 0) + 1
            latency_ms = transcript.latency_ms if transcript else 0
            result_row = {
                "case_id": case.id,
                "name": case.name,
                "category": case.category,
                "verdict": judgement.verdict,
                "severity": judgement.severity,
                "reason": judgement.reason,
            }
            result_rows.append(result_row)
            record = TestResult(
                run_id=run.id,
                case_id=case.id,
                verdict=judgement.verdict,
                severity=judgement.severity,
                confidence=judgement.confidence,
                reason=judgement.reason,
                latency_ms=latency_ms,
                evidence={
                    "messages": transcript.messages if transcript else [],
                    "raw_response_count": len(transcript.raw_responses) if transcript else 0,
                    "references": judgement.references,
                    "error": error_message,
                },
            )
            session.add(record)
            await session.commit()
            case_result = {
                **result_row,
                "confidence": judgement.confidence,
                "latency_ms": latency_ms,
                "error": error_message,
            }
            await append_short_term(run.id, {"event": "case_result", **case_result})
            yield sse("case_result", case_result)

        run.status = "completed_with_errors" if errors else "completed"
        run.finished_at = datetime.now(timezone.utc)
        failed_cases = [
            row for row in result_rows if row["verdict"] in {"FAIL", "UNKNOWN"}
        ]
        run.summary = {
            "counts": counts,
            "total": len(cases),
            "errors": errors,
            "categories": covered_categories,
            "failed_cases": failed_cases,
            "text": build_summary_text(
                target.name,
                len(cases),
                counts,
                errors,
                failed_cases,
                covered_categories,
            ),
        }
        await session.commit()
        try:
            await asyncio.wait_for(
                remember_target_profile(target, run.id, run.summary, result_rows),
                timeout=settings.memory_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("Long-term memory write degraded: %s", type(exc).__name__)
        run_completed = {"run_id": run.id, "summary": run.summary}
        await append_short_term(run.id, {"event": "run_completed", **run_completed})
        yield sse("run_completed", run_completed)

