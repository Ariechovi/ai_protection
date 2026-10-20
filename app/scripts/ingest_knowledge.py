import asyncio
from pathlib import Path

from app.services.rag import ingest_file

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
DOCS = [
    ("prompt_boundary.md", "prompt_boundary"),
    ("data_protection.md", "data_protection"),
    ("tool_boundary.md", "tool_boundary"),
    ("evaluation_policy.md", "evaluation_policy"),
]


async def main() -> None:
    for filename, category in DOCS:
        path = KNOWLEDGE_DIR / filename
        count = await ingest_file(path, category=category)
        print(f"{filename}: {count} chunks")


if __name__ == "__main__":
    asyncio.run(main())

