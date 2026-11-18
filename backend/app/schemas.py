
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    database: str


class DatasetSummary(BaseModel):
    dataset: str
    records: int


class PolicySummary(BaseModel):
    version: str
    effective_date: str
    status: str
    source_document: str | None = None


class ProcurementProcessRequest(BaseModel):
    """
    Optional custom purchase request batch.

    If requests is omitted or null, the API processes the
    imported sample_pr_batch dataset.
    """

    requests: list[dict[str, Any]] | None = Field(
        default=None,
        max_length=5000,
        description=(
            "Purchase request lines to process. "
            "If omitted, the imported sample PR batch is used."
        ),
    )
