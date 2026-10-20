import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select

from app.db.engine import get_session_factory
from app.db.models import KnowledgeChunk
from app.services.llm import build_embeddings


@dataclass
class KnowledgeHit:
    id: str
    title: str
    category: str
    content: str
    source_ref: str | None
    score: float

    def as_reference(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "source_ref": self.source_ref,
            "score": round(self.score, 4),
        }


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


async def ingest_text(
    title: str,
    category: str,
    content: str,
    source_ref: str | None = None,
) -> int:
    chunks = chunk_text(content)
    if not chunks:
        return 0
    embeddings = await asyncio.to_thread(build_embeddings().embed_documents, chunks)
    session_factory = get_session_factory()
    async with session_factory() as session:
        if source_ref:
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.source_ref == source_ref)
            )
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True), start=1):
            session.add(
                KnowledgeChunk(
                    title=f"{title} #{index}",
                    category=category,
                    content=chunk,
                    embedding=embedding,
                    source_ref=source_ref,
                )
            )
        await session.commit()
    return len(chunks)


async def ingest_file(path: Path, category: str, title: str | None = None) -> int:
    return await ingest_text(
        title=title or path.stem,
        category=category,
        content=path.read_text(encoding="utf-8"),
        source_ref=str(path),
    )


async def search_knowledge(query: str, top_k: int = 3) -> list[KnowledgeHit]:
    query_embedding = await asyncio.to_thread(build_embeddings().embed_query, query)
    session_factory = get_session_factory()
    async with session_factory() as session:
        distance = KnowledgeChunk.embedding.cosine_distance(query_embedding).label("distance")
        result = await session.execute(
            select(KnowledgeChunk, distance)
            .order_by(distance)
            .limit(top_k)
        )
        hits: list[KnowledgeHit] = []
        for chunk, distance_value in result.all():
            hits.append(
                KnowledgeHit(
                    id=chunk.id,
                    title=chunk.title,
                    category=chunk.category,
                    content=chunk.content,
                    source_ref=chunk.source_ref,
                    score=1.0 - float(distance_value),
                )
            )
        return hits

