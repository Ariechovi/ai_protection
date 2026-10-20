from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from app.services.rag import ingest_text, search_knowledge

router = APIRouter(prefix="/api/v1", tags=["knowledge"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "uploads"


@router.post("/knowledge/ingest")
async def ingest_knowledge(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("security"),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / (file.filename or "knowledge.md")
    content = await file.read()
    target.write_bytes(content)
    count = await ingest_text(
        title=title,
        category=category,
        content=content.decode("utf-8"),
        source_ref=str(target),
    )
    return {"title": title, "category": category, "chunks": count}


@router.get("/knowledge/search")
async def search(q: str, top_k: int = 3):
    return [hit.as_reference() | {"content": hit.content} for hit in await search_knowledge(q, top_k)]

