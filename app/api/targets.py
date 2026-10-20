from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Target
from app.schemas import TargetCreate, TargetRead

router = APIRouter(prefix="/api/v1", tags=["targets"])


@router.post("/targets", response_model=TargetRead)
async def create_target(payload: TargetCreate, session: AsyncSession = Depends(get_session)):
    target = Target(**payload.model_dump())
    session.add(target)
    await session.commit()
    await session.refresh(target)
    return target


@router.get("/targets", response_model=list[TargetRead])
async def list_targets(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Target).order_by(Target.created_at.desc()))
    return list(result.scalars().all())

