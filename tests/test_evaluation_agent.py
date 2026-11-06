import asyncio
from types import SimpleNamespace

from app.db.models import Target as DbTarget
from app.db.models import TestCase as DbTestCase
from app.services import evaluation_agent


class RecordingAdapter:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def run_steps(self, steps):
        from app.services.target_adapter import Transcript

        self.seen.append(steps[0])
        return Transcript(
            messages=[
                {"role": "user", "content": steps[0]},
                {"role": "assistant", "content": "safe"},
            ],
            latency_ms=1,
            raw_responses=[],
        )


class RecordingSession:
    def __init__(self) -> None:
        self.records: list[object] = []
        self.commits = 0

    def add(self, value) -> None:
        self.records.append(value)

    async def commit(self) -> None:
        self.commits += 1


def make_case(
    case_id: str,
    *,
    severity: str = "medium",
    category: str = "prompt_boundary",
) -> DbTestCase:
    return DbTestCase(
        id=case_id,
        name=f"case {case_id}",
        category=category,
        severity=severity,
        description=f"description {case_id}",
        steps=[f"step {case_id}"],
        expected_behavior="safe",
    )


def settings(**overrides):
    values = {
        "agent_runtime_mode": "deterministic",
        "agent_max_steps": 6,
        "agent_planner_timeout_seconds": 1,
        "target_timeout_seconds": 1,
        "judge_timeout_seconds": 1,
        "memory_timeout_seconds": 1,
        "model_api_key": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_planner_fallback_prioritizes_high_severity():
    cases = [
        make_case("medium-case", severity="medium"),
        make_case("high-case", severity="high"),
    ]

    selected, source = asyncio.run(
        evaluation_agent.choose_next_case(cases, [], settings())
    )

    assert selected.id == "high-case"
    assert source == "fallback"


def test_planner_rejects_case_outside_allowlist(monkeypatch):
    cases = [
        make_case("allowed-high", severity="high"),
        make_case("allowed-low", severity="low"),
    ]
    configured = settings(
        agent_runtime_mode="llm",
        model_api_key="test-key",
    )

    class FakeModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"case_id": "outside-case"}')

    monkeypatch.setattr(evaluation_agent, "build_chat_model", lambda: FakeModel())

    selected, source = asyncio.run(
        evaluation_agent.choose_next_case(cases, [], configured)
    )

    assert selected.id == "allowed-high"
    assert source == "fallback"


def test_planner_accepts_only_whitelisted_llm_case(monkeypatch):
    cases = [
        make_case("first", severity="high"),
        make_case("second", severity="low"),
    ]
    configured = settings(
        agent_runtime_mode="llm",
        model_api_key="test-key",
    )

    class FakeModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='{"case_id": "second"}')

    monkeypatch.setattr(evaluation_agent, "build_chat_model", lambda: FakeModel())

    selected, source = asyncio.run(
        evaluation_agent.choose_next_case(cases, [], configured)
    )

    assert selected.id == "second"
    assert source == "llm"


def test_graph_runs_bounded_plan_execute_persist_loop(monkeypatch):
    cases = [
        make_case("high-case", severity="high"),
        make_case("medium-case", severity="medium"),
        make_case("low-case", severity="low"),
    ]
    target = DbTarget(
        id="target-1",
        name="mock target",
        endpoint="mock://secure",
        model="mock-model",
        authorized=True,
        allowed_categories=["prompt_boundary"],
    )
    session = RecordingSession()
    adapter = RecordingAdapter()
    configured = settings(agent_max_steps=2)

    async def fake_context(target_id, run_id, query):
        return evaluation_agent.MemoryContext(
            short_term=[{"event": "run_started"}],
            previous_summary={"text": "previous"},
            long_term=[evaluation_agent.MemoryHit("history", 0.8)],
        )

    async def fake_judge(case, transcript, memory_text=""):
        return evaluation_agent.JudgeResult(
            verdict="PASS",
            severity=case.severity,
            confidence=0.9,
            reason="safe",
        )

    monkeypatch.setattr(evaluation_agent, "load_context", fake_context)
    monkeypatch.setattr(evaluation_agent, "judge_case", fake_judge)

    agent = evaluation_agent.EvaluationAgent(
        target=target,
        cases=cases,
        run_id="run-1",
        session=session,
        settings=configured,
        adapter=adapter,
    )

    async def collect():
        return [item async for item in agent.stream()]

    items = asyncio.run(collect())
    final = items[-1]
    events = [item["event"] for item in items[:-1]]

    assert adapter.seen == ["step high-case", "step medium-case"]
    assert events.count("case_planned") == 2
    assert events.count("case_started") == 2
    assert events.count("case_result") == 2
    assert final["event"] == "_completed_state"
    assert final["data"]["summary"]["total"] == 2
    assert final["data"]["summary"]["agent"]["iterations"] == 2
    assert len(session.records) == 2
