from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import TestCase
from app.schemas import TestCaseRead

router = APIRouter(prefix="/api/v1", tags=["test-cases"])


@router.get("/test-cases", response_model=list[TestCaseRead])
async def list_test_cases(category: str | None = None, session: AsyncSession = Depends(get_session)):
    query = select(TestCase).where(TestCase.enabled.is_(True)).order_by(TestCase.id)
    if category:
        query = query.where(TestCase.category == category)
    result = await session.execute(query)
    return list(result.scalars().all())

