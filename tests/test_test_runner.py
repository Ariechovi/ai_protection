import asyncio
from types import SimpleNamespace

from app.db.models import TestCase as DbTestCase
from app.services.judge import JudgeResult
from app.services import test_runner
from app.services.target_adapter import Transcript


class FailingAdapter:
    async def run_steps(self, steps):
        raise TimeoutError("target timed out")


class CapturingAdapter:
    async def run_steps(self, steps):
        return Transcript(
            messages=[
                {"role": "user", "content": steps[0]},
                {"role": "assistant", "content": "safe"},
            ],
            latency_ms=5,
            raw_responses=[],
        )


def make_case() -> DbTestCase:
    return DbTestCase(
        id="case-1",
        name="timeout case",
        category="prompt_boundary",
        severity="medium",
        description="timeout test",
        steps=["hello"],
        expected_behavior="safe",
    )


def test_case_failure_returns_unknown_and_does_not_raise():
    settings = SimpleNamespace(
        target_timeout_seconds=0.01,
        judge_timeout_seconds=0.01,
    )
    transcript, judgement, error = asyncio.run(
        test_runner.execute_case(FailingAdapter(), make_case(), settings)
    )
    assert transcript is None
    assert judgement.verdict == "UNKNOWN"
    assert error == "target error: TimeoutError"


def test_execute_case_passes_memory_context_to_judge(monkeypatch):
    captured = {}

    async def fake_judge(case, transcript, memory_text=""):
        captured["memory_text"] = memory_text
        return JudgeResult(
            verdict="PASS",
            severity=case.severity,
            confidence=0.9,
            reason="符合预期",
        )

    monkeypatch.setattr(test_runner, "judge_case", fake_judge)
    settings = SimpleNamespace(
        target_timeout_seconds=1,
        judge_timeout_seconds=1,
    )

    transcript, judgement, error = asyncio.run(
        test_runner.execute_case(
            CapturingAdapter(),
            make_case(),
            settings,
            memory_text="历史失败集中在提示边界",
        )
    )

    assert transcript is not None
    assert judgement.verdict == "PASS"
    assert error is None
    assert captured["memory_text"] == "历史失败集中在提示边界"

