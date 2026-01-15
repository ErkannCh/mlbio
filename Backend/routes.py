from __future__ import annotations

import json
import queue

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from Backend.job_manager import job_manager
from Backend.schemas import InfoResponse, JobStatusResponse, RunRequest, StartRunResponse
from Backend.streaming import stream_broker

router = APIRouter(prefix="/fl", tags=["federated-learning"])


@router.get("/info", response_model=InfoResponse)
def info() -> InfoResponse:
    return InfoResponse(
        dataset="HAM10000",
        expected_total_size=10015,
        default_test_size=500,
        recommended_fractions=[1.0, 0.5, 0.1],
    )


@router.post("/run", response_model=StartRunResponse)
def run(req: RunRequest) -> StartRunResponse:
    # Helpful trace to ensure frontend parameters are received as expected.
    try:
        payload = req.model_dump()  # pydantic v2
    except Exception:  # noqa: BLE001
        payload = req.dict()  # pydantic v1 fallback
    print(f"POST /fl/run payload={payload}", flush=True)
    job_id = job_manager.submit(req)
    return StartRunResponse(job_id=job_id)


@router.get("/stream/{job_id}")
async def run_stream(job_id: str) -> StreamingResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    q = stream_broker.subscribe(job_id)

    def _dump_results() -> list[dict] | None:
        if not job.results:
            return None
        out: list[dict] = []
        for r in job.results:
            try:
                out.append(r.model_dump())  # pydantic v2
            except Exception:  # noqa: BLE001
                out.append(r.dict())  # pydantic v1
        return out

    initial = {
        "type": "job_status",
        "job": {
            "job_id": job.job_id,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "progress": job.progress,
            "message": job.message,
            "results": _dump_results(),
        },
    }

    async def event_gen():
        try:
            yield f"data: {json.dumps(initial, ensure_ascii=False, separators=(',', ':'))}\n\n"
            while True:
                try:
                    msg = await anyio.to_thread.run_sync(lambda: q.get(timeout=15))
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {msg}\n\n"
        finally:
            stream_broker.unsubscribe(job_id, q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/run/{job_id}", response_model=JobStatusResponse)
def run_status(job_id: str) -> JobStatusResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        progress=job.progress,
        message=job.message,
        results=job.results,
    )
