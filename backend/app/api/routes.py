
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import SourceRecord, PolicyVersion
from app.schemas import (
    HealthResponse,
    DatasetSummary,
    PolicySummary,
    ProcurementProcessRequest,
)
from app.services.importer import import_all_source_data

from app.services.procurement.policy_service import PolicyService
from app.services.procurement.orchestration_service import (
    ProcurementOrchestrationService,
)


router = APIRouter()


# ============================================================
# EXISTING ENDPOINTS
# ============================================================

@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return HealthResponse(
            status="ok",
            database="connected",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from exc


@router.get("/data/summary", response_model=list[DatasetSummary])
def data_summary(db: Session = Depends(get_db)):
    rows = (
        db.query(
            SourceRecord.dataset,
            func.count(SourceRecord.id),
        )
        .group_by(SourceRecord.dataset)
        .order_by(SourceRecord.dataset)
        .all()
    )

    return [
        DatasetSummary(dataset=name, records=count)
        for name, count in rows
    ]


@router.post("/data/import")
def import_task_kit_data(db: Session = Depends(get_db)):
    source_dir = Path(settings.source_data_dir).resolve()

    try:
        counts = import_all_source_data(db, source_dir)

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "message": "Task-kit CSV data imported",
        "counts": counts,
        "total_records": sum(counts.values()),
    }


@router.get("/policies", response_model=list[PolicySummary])
def list_policies(db: Session = Depends(get_db)):
    policies = (
        db.query(PolicyVersion)
        .order_by(PolicyVersion.created_at.desc())
        .all()
    )

    return [
        PolicySummary(
            version=policy.version,
            effective_date=policy.effective_date,
            status=policy.status,
            source_document=policy.source_document,
        )
        for policy in policies
    ]


@router.get("/data/{dataset}")
def get_dataset(
    dataset: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 500",
        )

    allowed = {
        "item_master",
        "supplier_master",
        "po_history",
        "plants",
        "contract_register",
        "contract_lines",
        "sample_pr_batch",
    }

    if dataset not in allowed:
        raise HTTPException(
            status_code=404,
            detail="Unknown dataset",
        )

    rows = (
        db.query(SourceRecord)
        .filter(SourceRecord.dataset == dataset)
        .order_by(SourceRecord.id)
        .limit(limit)
        .all()
    )

    return {
        "dataset": dataset,
        "records": [row.payload for row in rows],
        "returned": len(rows),
    }


# ============================================================
# PROCUREMENT API HELPERS
# ============================================================

def load_dataset(
    db: Session,
    dataset_name: str,
) -> pd.DataFrame:
    """
    Load an entire imported dataset from SourceRecord.
    """

    rows = (
        db.query(SourceRecord)
        .filter(SourceRecord.dataset == dataset_name)
        .order_by(SourceRecord.id)
        .all()
    )

    if not rows:
        raise ValueError(
            f"Dataset '{dataset_name}' is empty or has not been imported. "
            "Run POST /api/data/import first."
        )

    return pd.DataFrame(
        [row.payload for row in rows]
    )


def make_json_safe(value: Any) -> Any:
    """
    Convert pandas, NumPy and datetime values into JSON-safe values.
    """

    if value is None:
        return None

    if isinstance(value, (pd.Timestamp, datetime, date)):
        if pd.isna(value):
            return None
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            make_json_safe(item)
            for item in value
        ]

    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass

    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (TypeError, ValueError):
        pass

    return value


def dataframe_to_records(
    dataframe: pd.DataFrame,
) -> list[dict]:
    """
    Convert a DataFrame into JSON-safe record dictionaries.
    """

    if dataframe is None or dataframe.empty:
        return []

    records = dataframe.to_dict(orient="records")

    return [
        make_json_safe(record)
        for record in records
    ]


# ============================================================
# PROCUREMENT PROCESSING ENDPOINT
# ============================================================

@router.post("/procurement/process")
def process_procurement_requests(
    payload: ProcurementProcessRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Process a purchase request batch through the complete
    policy-driven procurement workflow.

    Request body:
        {
            "requests": [
                {
                    "pr_no": "PR-EXAMPLE-001",
                    "pr_line": "1",
                    "created_at": "2026-11-18",
                    "plant": "PUN1",
                    "item_code": "ITM-1001",
                    "need_by_date": "2026-11-25",
                    "quantity": 10,
                    "urgency": "Normal"
                }
            ]
        }

    If requests is omitted, the imported sample_pr_batch is used.
    """

    try:
        # ----------------------------------------------------
        # 1. LOAD ACTIVE POLICY
        # ----------------------------------------------------

        policy_service = PolicyService(db)

        active_policy = policy_service.get_active_policy()

        policy_data = active_policy["policy_data"]

        ranking_weights = (
            policy_service.get_supplier_ranking_weights()
        )

        # ----------------------------------------------------
        # 2. LOAD IMPORTED DATASETS
        # ----------------------------------------------------

        item_master = load_dataset(
            db,
            "item_master",
        )

        supplier_master = load_dataset(
            db,
            "supplier_master",
        )

        po_history = load_dataset(
            db,
            "po_history",
        )

        plants = load_dataset(
            db,
            "plants",
        )

        contract_register = load_dataset(
            db,
            "contract_register",
        )

        contract_lines = load_dataset(
            db,
            "contract_lines",
        )

        # ----------------------------------------------------
        # 3. LOAD PURCHASE REQUESTS
        # ----------------------------------------------------

        if payload is not None and payload.requests is not None:

            if not payload.requests:
                raise HTTPException(
                    status_code=400,
                    detail="The requests list cannot be empty.",
                )

            requests_df = pd.DataFrame(
                payload.requests
            )

            request_source = "API_REQUEST"

        else:

            requests_df = load_dataset(
                db,
                "sample_pr_batch",
            )

            request_source = "IMPORTED_SAMPLE_BATCH"

        # ----------------------------------------------------
        # 4. INITIALIZE ORCHESTRATION SERVICE
        # ----------------------------------------------------

        orchestration = ProcurementOrchestrationService(
            policy_data=policy_data,
            item_master=item_master,
            plants=plants,
            supplier_master=supplier_master,
            po_history=po_history,
            contract_register=contract_register,
            contract_lines=contract_lines,
            ranking_weights=ranking_weights,
        )

        # ----------------------------------------------------
        # 5. PROCESS PROCUREMENT REQUESTS
        # ----------------------------------------------------

        results = orchestration.process_requests(
            requests_df
        )

        # ----------------------------------------------------
        # 6. PREPARE API RESPONSE
        # ----------------------------------------------------

        requirement_results = dataframe_to_records(
            results["requirement_results"]
        )

        final_line_results = dataframe_to_records(
            results["final_line_results"]
        )

        contract_allocations = dataframe_to_records(
            results["contract_allocations"]
        )

        invalid_lines = dataframe_to_records(
            results["invalid_lines"]
        )

        contract_balances = dataframe_to_records(
            results["contract_balances"]
        )

        # Route summary.
        route_summary = {}

        if not results["requirement_results"].empty:
            route_counts = (
                results["requirement_results"]["route"]
                .fillna("NOT_DECIDED")
                .value_counts()
            )

            route_summary = {
                str(route): int(count)
                for route, count in route_counts.items()
            }

        # Decision summary.
        decision_summary = {}

        if not results["requirement_results"].empty:
            decision_counts = (
                results["requirement_results"]["decision"]
                .fillna("NOT_DECIDED")
                .value_counts()
            )

            decision_summary = {
                str(decision): int(count)
                for decision, count in decision_counts.items()
            }

        return make_json_safe({
            "success": True,
            "message": "Procurement processing completed.",
            "request_source": request_source,

            "policy": {
                "version": active_policy["version"],
                "effective_date": active_policy["effective_date"],
            },

            "summary": {
                "total_input_lines": len(requests_df),
                "valid_lines": len(results["valid_lines"]),
                "invalid_lines": len(results["invalid_lines"]),
                "clubbed_lines": len(results["clubbed_lines"]),
                "consolidated_requirements": len(
                    results["requirement_summary"]
                ),
                "requirements_processed": len(
                    results["requirement_results"]
                ),
                "route_summary": route_summary,
                "decision_summary": decision_summary,
            },

            "invalid_lines": invalid_lines,
            "requirement_results": requirement_results,
            "contract_allocations": contract_allocations,
            "contract_balances": contract_balances,
            "final_line_results": final_line_results,

            "limitations": [
                (
                    "Contract allocations are calculated in memory "
                    "for this request and are not permanently reserved."
                ),
                (
                    "Procurement decisions and allocations are not yet "
                    "persisted as transaction or audit records."
                ),
            ],
        })

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Procurement processing failed: {str(exc)}",
        ) from exc
