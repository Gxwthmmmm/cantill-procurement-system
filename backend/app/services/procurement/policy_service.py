
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PolicyVersion


class PolicyService:
    """Loads the active procurement policy from the database."""

    def __init__(self, db: Session):
        self.db = db

    def get_active_policy(self) -> dict:
        statement = (
            select(PolicyVersion)
            .where(PolicyVersion.status == "active")
            .order_by(PolicyVersion.effective_date.desc())
        )

        policy_version = self.db.scalars(statement).first()

        if policy_version is None:
            raise ValueError("No active procurement policy found.")

        return {
            "version": policy_version.version,
            "effective_date": policy_version.effective_date,
            "policy_data": policy_version.policy_data,
        }

    def get_supplier_ranking_weights(self) -> dict:
        active_policy = self.get_active_policy()

        suppliers_policy = (
            active_policy["policy_data"].get("suppliers", {})
        )

        weights = suppliers_policy.get("ranking_weights")

        if not weights:
            raise ValueError(
                "Supplier ranking weights are missing from the active policy."
            )

        expected_factors = {
            "purchase_frequency",
            "purchase_recency",
            "contract_history",
            "on_time_delivery",
            "quality",
        }

        if set(weights.keys()) != expected_factors:
            raise ValueError(
                "Supplier ranking weights do not match the expected factors."
            )

        if any(
            not isinstance(weight, (int, float)) or weight < 0
            for weight in weights.values()
        ):
            raise ValueError("Supplier ranking weights must be non-negative numbers.")

        if abs(sum(weights.values()) - 1.0) > 0.000001:
            raise ValueError("Supplier ranking weights must total 1.0.")

        return weights
