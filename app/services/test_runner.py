import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db.engine import get_session_factory
from app.db.models import Target, TestCase, TestResult, TestRun
from app.services.judge import judge_case
from app.services.target_adapter import TargetAdapter


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

        query = select(TestCase).where(TestCase.enabled.is_(True))
        if categories:
            query = query.where(TestCase.category.in_(categories))
        result = await session.execute(
            query.order_by(TestCase.id).limit(settings.max_test_cases)
        )
        cases = list(result.scalars().all())
        run.status = "running"
        await session.commit()
        yield sse("run_started", {"run_id": run.id, "target": target.name, "count": len(cases)})

        counts = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0}
        adapter = TargetAdapter(target)
        for case in cases:
            yield sse("case_started", {"case_id": case.id, "name": case.name})
            try:
                transcript = await adapter.run_steps(case.steps)
                judgement = await judge_case(case, transcript)
            except Exception as exc:
                transcript = None
                judgement = None
                error_message = f"{type(exc).__name__}: {exc}"
                yield sse("error", {"case_id": case.id, "message": error_message})
                run.status = "failed"
                await session.commit()
                return

            counts[judgement.verdict] = counts.get(judgement.verdict, 0) + 1
            record = TestResult(
                run_id=run.id,
                case_id=case.id,
                verdict=judgement.verdict,
                severity=judgement.severity,
                confidence=judgement.confidence,
                reason=judgement.reason,
                latency_ms=transcript.latency_ms,
                evidence={
                    "messages": transcript.messages,
                    "raw_response_count": len(transcript.raw_responses),
                    "references": judgement.references,
                },
            )
            session.add(record)
            await session.commit()
            yield sse(
                "case_result",
                {
                    "case_id": case.id,
                    "name": case.name,
                    "verdict": judgement.verdict,
                    "severity": judgement.severity,
                    "confidence": judgement.confidence,
                    "reason": judgement.reason,
                    "latency_ms": transcript.latency_ms,
                },
            )

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.summary = {"counts": counts, "total": len(cases)}
        await session.commit()
        yield sse("run_completed", {"run_id": run.id, "summary": run.summary})

