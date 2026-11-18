
from app.db.session import SessionLocal
from app.services.procurement.policy_service import PolicyService


def main():
    db = SessionLocal()

    try:
        service = PolicyService(db)

        active_policy = service.get_active_policy()
        weights = service.get_supplier_ranking_weights()

        print("\nACTIVE POLICY")
        print("-------------------------")
        print("Version:", active_policy["version"])
        print("Effective date:", active_policy["effective_date"])

        print("\nSUPPLIER RANKING WEIGHTS")
        print("-------------------------")

        for factor, weight in weights.items():
            print(f"{factor}: {weight:.0%}")

        print("\nTotal weight:", f"{sum(weights.values()):.0%}")
        print("\nPolicy service test completed successfully.")

    except Exception as error:
        print("\nPOLICY SERVICE TEST FAILED")
        print("Error:", error)

    finally:
        db.close()


if __name__ == "__main__":
    main()
