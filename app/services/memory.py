import asyncio
import json
import logging
from dataclasses import dataclass, field

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.engine import get_session_factory
from app.db.models import Memory, TestRun
from app.services.llm import build_embeddings
from app.services.redaction import redact_text

logger = logging.getLogger(__name__)
_redis_client: aioredis.Redis | None = None


@dataclass
class MemoryHit:
    content: str
    score: float


@dataclass
class MemoryContext:
    short_term: list[dict] = field(default_factory=list)
    previous_summary: dict | None = None
    long_term: list[MemoryHit] = field(default_factory=list)

    def render(self) -> str:
        sections = []
        if self.short_term:
            sections.append(
                "短期记忆（当前运行最近事件）：\n"
                + "\n".join(json.dumps(item, ensure_ascii=False) for item in self.short_term)
            )
        if self.previous_summary:
            sections.append(
                "对话摘要记忆（上一次评测）：\n"
                + json.dumps(_compact_summary(self.previous_summary), ensure_ascii=False)
            )
        if self.long_term:
            sections.append(
                "长期记忆（目标历史画像）：\n"
                + "\n".join(f"- {hit.content}" for hit in self.long_term)
            )
        rendered = "\n\n".join(sections) if sections else "（暂无历史记忆）"
        return redact_text(rendered)


def _compact_summary(summary: dict) -> dict:
    """Keep prompt context small; detailed evidence remains in test_results."""
    keys = ("text", "counts", "errors", "categories")
    return {key: summary[key] for key in keys if summary.get(key) is not None}


def _redact_value(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


async def close_memory() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def append_short_term(run_id: str, event: dict, limit: int = 20) -> None:
    """Keep only compact events; never put raw target transcripts in Redis."""
    key = f"ai_protection:run:{run_id}:context"
    try:
        client = _get_redis()
        safe_event = _redact_value(event)
        await client.rpush(key, json.dumps(safe_event, ensure_ascii=False))
        await client.ltrim(key, -limit, -1)
        await client.expire(key, 86400)
    except Exception as exc:
        logger.warning("Redis short-term write failed: %s", type(exc).__name__)


async def read_short_term(run_id: str, limit: int = 10) -> list[dict]:
    key = f"ai_protection:run:{run_id}:context"
    try:
        values = await _get_redis().lrange(key, -limit, -1)
        items = []
        for value in values:
            try:
                items.append(_redact_value(json.loads(value)))
            except (TypeError, json.JSONDecodeError):
                continue
        return items
    except Exception as exc:
        logger.warning("Redis short-term read failed: %s", type(exc).__name__)
        return []


async def _get_previous_summary(
    session: AsyncSession,
    target_id: str,
    current_run_id: str,
) -> dict | None:
    result = await session.execute(
        select(TestRun)
        .where(
            TestRun.target_id == target_id,
            TestRun.id != current_run_id,
            TestRun.status.in_(["completed", "completed_with_errors"]),
            TestRun.summary.is_not(None),
        )
        .order_by(TestRun.finished_at.desc().nullslast())
        .limit(1)
    )
    previous = result.scalar_one_or_none()
    return previous.summary if previous else None


async def _retrieve_long_term(
    session: AsyncSession,
    target_id: str,
    query: str,
    top_k: int = 3,
) -> list[MemoryHit]:
    try:
        embedding = await asyncio.to_thread(
            build_embeddings().embed_query,
            query,
        )
        distance = Memory.embedding.cosine_distance(embedding).label("distance")
        result = await session.execute(
            select(Memory, distance)
            .where(
                Memory.target_id == target_id,
                Memory.memory_type == "target_profile",
            )
            .order_by(distance)
            .limit(top_k)
        )
        return [
            MemoryHit(content=memory.content, score=1.0 - float(value))
            for memory, value in result.all()
        ]
    except Exception as exc:
        logger.warning("Long-term memory retrieval failed: %s", type(exc).__name__)
        return []


async def load_context(target_id: str, run_id: str, query: str) -> MemoryContext:
    short_term = await read_short_term(run_id)
    previous_summary = None
    long_term: list[MemoryHit] = []
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            previous_summary = await _get_previous_summary(session, target_id, run_id)
            long_term = await _retrieve_long_term(session, target_id, query)
    except Exception as exc:
        logger.warning("PostgreSQL memory read failed: %s", type(exc).__name__)
    return MemoryContext(
        short_term=short_term,
        previous_summary=previous_summary,
        long_term=long_term,
    )


def build_summary_text(
    target_name: str,
    total: int,
    counts: dict,
    errors: int,
    failed_cases: list[dict],
    categories: list[str] | None = None,
) -> str:
    failed = "、".join(str(item.get("name", "未命名")) for item in failed_cases) or "无"
    scope = "、".join(categories or []) or "未记录"
    text = (
        f"目标 {target_name} 本次评测共 {total} 条："
        f"PASS {counts.get('PASS', 0)}，FAIL {counts.get('FAIL', 0)}，"
        f"UNKNOWN {counts.get('UNKNOWN', 0)}，执行错误 {errors}。"
        f"覆盖范围：{scope}。失败/需关注用例：{failed}。"
    )
    return redact_text(text)


async def remember_target_profile(
    target,
    run_id: str,
    summary: dict,
    result_rows: list[dict],
) -> bool:
    """Persist a summarized target profile; failure must not fail the test run."""
    content = redact_text(
        f"目标 {target.name}，模型 {target.model}。"
        f"{summary.get('text', '')}"
        + "\n"
        + "\n".join(
            f"[{row.get('category', 'unknown')}] {row['case_id']} "
            f"{row['name']}: {row['verdict']} - {row['reason']}"
            for row in result_rows
        )
    )
    try:
        embedding = await asyncio.to_thread(
            build_embeddings().embed_query,
            content,
        )
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                Memory(
                    target_id=target.id,
                    memory_type="target_profile",
                    content=content,
                    embedding=embedding,
                    metadata_={
                        "run_id": run_id,
                        "kind": "evaluation_summary",
                        "total": summary.get("total", 0),
                    },
                )
            )
            await session.commit()
        return True
    except Exception as exc:
        logger.warning("Long-term memory write failed: %s", type(exc).__name__)
        return False

