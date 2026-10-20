from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db.models import Target, TestResult, TestRun
from app.schemas import ResultRead, RunCreate, RunRead
from app.services.test_runner import run_stream

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.post("/runs")
async def create_run(payload: RunCreate, session: AsyncSession = Depends(get_session)):
    target = await session.get(Target, payload.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")
    if not target.authorized:
        raise HTTPException(status_code=403, detail="target is not authorized for evaluation")
    run = TestRun(target_id=target.id, status="pending")
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return StreamingResponse(
        run_stream(run.id, payload.categories),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/runs/{run_id}/results", response_model=list[ResultRead])
async def get_run_results(run_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(TestResult).where(TestResult.run_id == run_id))
    return list(result.scalars().all())

