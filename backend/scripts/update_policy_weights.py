
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import PolicyVersion


RANKING_WEIGHTS = {
    "purchase_frequency": 0.20,
    "purchase_recency": 0.15,
    "contract_history": 0.20,
    "on_time_delivery": 0.25,
    "quality": 0.20,
}


def main():
    db = SessionLocal()

    try:
        policy = db.scalar(
            select(PolicyVersion)
            .where(PolicyVersion.version == "5.0")
            .with_for_update()
        )

        if policy is None:
            raise ValueError("Policy version 5.0 was not found.")

        if policy.status != "active":
            raise ValueError(
                f"Policy 5.0 is not active. Current status: {policy.status}"
            )

        policy_data = dict(policy.policy_data or {})
        suppliers = dict(policy_data.get("suppliers", {}))

        suppliers["ranking_weights"] = RANKING_WEIGHTS
        policy_data["suppliers"] = suppliers

        policy.policy_data = policy_data
        policy.change_summary = (
            "Added supplier ranking weights to policy v5.0 "
            "for implementation configuration."
        )

        db.commit()

        print("Successfully updated policy v5.0.")
        print("Supplier ranking weights:")

        for factor, weight in RANKING_WEIGHTS.items():
            print(f"{factor}: {weight:.0%}")

    except Exception as error:
        db.rollback()
        print("Policy update failed:", error)

    finally:
        db.close()


if __name__ == "__main__":
    main()
