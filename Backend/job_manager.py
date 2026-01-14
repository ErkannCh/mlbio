from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Callable
from uuid import uuid4

from concurrent.futures import Future, ThreadPoolExecutor

from Backend.schemas import RunRequest, RunResult
from Backend.service import run_fl_sweep


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    job_id: str
    req: RunRequest
    status: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: float = 0.0
    message: str | None = None
    results: list[RunResult] | None = None


class JobManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, Job] = {}
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._futures: dict[str, Future] = {}

    def submit(self, req: RunRequest) -> str:
        job_id = uuid4().hex
        job = Job(
            job_id=job_id,
            req=req,
            status="queued",
            created_at=_now(),
            progress=0.0,
        )
        with self._lock:
            self._jobs[job_id] = job
        fut = self._executor.submit(self._run_job, job_id)
        with self._lock:
            self._futures[job_id] = fut
        return job_id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _set_progress(self, job_id: str, progress: float, message: str | None = None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.progress = max(0.0, min(1.0, float(progress)))
            if message is not None:
                job.message = message

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = _now()

        total = max(1, len(job.req.fractions))

        def progress_cb(done: int, result: RunResult | None) -> None:
            msg = None
            if result is not None:
                msg = f"Finished scenario {done}/{total}"
            self._set_progress(job_id, done / total, msg)

        try:
            results = run_fl_sweep(
                n_clients=job.req.n_clients,
                rounds=job.req.rounds,
                epochs=job.req.epochs,
                lr=job.req.lr,
                test_size=job.req.test_size,
                fractions=job.req.fractions,
                progress_cb=progress_cb,
            )
            with self._lock:
                job = self._jobs[job_id]
                job.status = "succeeded"
                job.results = results
                job.progress = 1.0
                job.finished_at = _now()
                job.message = "Done"
        except Exception as e:  # noqa: BLE001
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.finished_at = _now()
                job.message = str(e)


job_manager = JobManager()

