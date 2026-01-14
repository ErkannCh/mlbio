from __future__ import annotations

from fastapi import APIRouter, HTTPException

from Backend.job_manager import job_manager
from Backend.schemas import InfoResponse, JobStatusResponse, RunRequest, StartRunResponse

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
    job_id = job_manager.submit(req)
    return StartRunResponse(job_id=job_id)


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
