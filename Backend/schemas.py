from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    n_clients: int = Field(ge=1, le=50, default=5)
    rounds: int = Field(ge=1, le=50, default=1)
    epochs: int = Field(ge=1, le=50, default=5)
    lr: float = Field(gt=0, default=5e-4)
    test_size: int = Field(ge=1, default=500)
    fractions: list[float] = Field(default_factory=lambda: [1.0, 0.5, 0.1])


class RunResult(BaseModel):
    fraction_of_1_over_n_clients: float
    n_data_per_client: int
    accuracy_percent: float


class RunResponse(BaseModel):
    n_clients: int
    results: list[RunResult]


class StartRunResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: float = Field(ge=0.0, le=1.0, default=0.0)
    message: str | None = None
    results: list[RunResult] | None = None


class InfoResponse(BaseModel):
    dataset: str
    expected_total_size: int
    default_test_size: int
    recommended_fractions: list[float]
