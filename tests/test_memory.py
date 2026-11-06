import asyncio
import json
from types import SimpleNamespace

from app.db.models import Memory
from app.services import memory


class FakeRedis:
    def __init__(self) -> None:
        self.values: list[str] = []
        self.trim: tuple[int, int] | None = None
        self.expiry: int | None = None

    async def rpush(self, key: str, value: str) -> None:
        self.values.append(value)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        self.trim = (start, end)

    async def expire(self, key: str, seconds: int) -> None:
        self.expiry = seconds

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        return list(self.values)


class FakeResult:
    def __init__(self, *, scalar=None, rows=None) -> None:
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.scalar

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self.results = list(results or [])
        self.added: list[object] = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return self.results.pop(0)

    def add(self, value) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


class FakeEmbeddings:
    def embed_query(self, query: str) -> list[float]:
        return [0.1] * 1024

    def fail(self, query: str) -> list[float]:
        raise RuntimeError("embedding unavailable")


def test_memory_context_renders_three_layers_and_redacts_credentials():
    context = memory.MemoryContext(
        short_term=[{"event": "case_result", "reason": "api_key=short-secret"}],
        previous_summary={
            "text": "PASS 1，FAIL 1",
            "counts": {"PASS": 1, "FAIL": 1, "UNKNOWN": 0},
            "failed_cases": [{"reason": "password=summary-secret"}],
        },
        long_term=[memory.MemoryHit(content="token sk-longsecret123", score=0.8)],
    )

    text = context.render()

    assert "短期记忆" in text
    assert "对话摘要记忆" in text
    assert "长期记忆" in text
    assert "short-secret" not in text
    assert "longsecret123" not in text
    assert "summary-secret" not in text


def test_build_summary_text_records_scope_counts_and_failed_cases():
    text = memory.build_summary_text(
        "测试目标",
        3,
        {"PASS": 1, "FAIL": 1, "UNKNOWN": 1},
        1,
        [{"name": "提示词泄露"}],
        ["prompt_boundary", "tool_boundary"],
    )

    assert "共 3 条" in text
    assert "PASS 1" in text
    assert "FAIL 1" in text
    assert "UNKNOWN 1" in text
    assert "执行错误 1" in text
    assert "prompt_boundary、tool_boundary" in text
    assert "提示词泄露" in text


def test_short_term_redis_write_redacts_and_sets_retention(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(memory, "_get_redis", lambda: client)

    asyncio.run(
        memory.append_short_term(
            "run-1",
            {"event": "error", "message": "password=should-not-leak"},
        )
    )

    payload = json.loads(client.values[0])
    assert "should-not-leak" not in payload["message"]
    assert payload["message"].endswith("[REDACTED_SECRET]")
    assert client.trim == (-20, -1)
    assert client.expiry == 86400


def test_short_term_read_skips_invalid_json(monkeypatch):
    client = FakeRedis()
    client.values = [
        json.dumps({"message": "api_key=should-not-leak"}),
        "not-json",
    ]
    monkeypatch.setattr(memory, "_get_redis", lambda: client)

    items = asyncio.run(memory.read_short_term("run-1", limit=5))

    assert len(items) == 1
    assert "should-not-leak" not in items[0]["message"]


def test_load_context_combines_all_three_layers(monkeypatch):
    session = FakeSession()

    async def fake_short_term(run_id, limit=10):
        return [{"event": "run_started"}]

    async def fake_previous(session, target_id, current_run_id):
        return {"text": "上次结果摘要"}

    async def fake_long_term(session, target_id, query, top_k=3):
        return [memory.MemoryHit(content="历史失败集中在提示边界", score=0.9)]

    monkeypatch.setattr(memory, "read_short_term", fake_short_term)
    monkeypatch.setattr(memory, "get_session_factory", lambda: FakeSessionFactory(session))
    monkeypatch.setattr(memory, "_get_previous_summary", fake_previous)
    monkeypatch.setattr(memory, "_retrieve_long_term", fake_long_term)

    context = asyncio.run(memory.load_context("target-1", "run-1", "提示边界"))

    assert context.short_term == [{"event": "run_started"}]
    assert context.previous_summary == {"text": "上次结果摘要"}
    assert context.long_term[0].content == "历史失败集中在提示边界"


def test_load_context_survives_database_failure(monkeypatch):
    async def fake_short_term(run_id, limit=10):
        return [{"event": "case_started"}]

    def broken_factory():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(memory, "read_short_term", fake_short_term)
    monkeypatch.setattr(memory, "get_session_factory", broken_factory)

    context = asyncio.run(memory.load_context("target-1", "run-1", "query"))

    assert context.short_term == [{"event": "case_started"}]
    assert context.previous_summary is None
    assert context.long_term == []


def test_previous_summary_uses_latest_completed_run(monkeypatch):
    previous = SimpleNamespace(summary={"text": "latest completed"})
    session = FakeSession([FakeResult(scalar=previous)])

    result = asyncio.run(
        memory._get_previous_summary(session, "target-1", "current-run")
    )

    assert result == {"text": "latest completed"}


def test_remember_target_profile_redacts_and_writes(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(
        memory,
        "get_session_factory",
        lambda: FakeSessionFactory(session),
    )
    monkeypatch.setattr(memory, "build_embeddings", lambda: FakeEmbeddings())
    target = SimpleNamespace(id="target-1", name="测试目标", model="deepseek-chat")
    summary = {
        "text": "共 1 条，FAIL 1",
        "total": 1,
    }
    rows = [
        {
            "case_id": "pb-001",
            "name": "提示词边界",
            "category": "prompt_boundary",
            "verdict": "FAIL",
            "reason": "泄露 sk-should-not-persist123",
        }
    ]

    stored = asyncio.run(
        memory.remember_target_profile(target, "run-1", summary, rows)
    )

    assert stored is True
    assert session.committed is True
    assert len(session.added) == 1
    record = session.added[0]
    assert isinstance(record, Memory)
    assert "should-not-persist123" not in record.content
    assert record.metadata_["run_id"] == "run-1"


def test_remember_target_profile_does_not_raise_on_embedding_failure(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(
        memory,
        "get_session_factory",
        lambda: FakeSessionFactory(session),
    )
    monkeypatch.setattr(memory, "build_embeddings", lambda: FakeEmbeddings())

    class BrokenEmbeddings(FakeEmbeddings):
        def embed_query(self, query: str) -> list[float]:
            raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(memory, "build_embeddings", lambda: BrokenEmbeddings())
    target = SimpleNamespace(id="target-1", name="测试目标", model="deepseek-chat")

    stored = asyncio.run(
        memory.remember_target_profile(
            target,
            "run-1",
            {"text": "summary", "total": 1},
            [],
        )
    )

    assert stored is False
    assert session.committed is False
