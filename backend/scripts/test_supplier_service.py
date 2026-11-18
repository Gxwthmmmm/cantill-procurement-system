
import pandas as pd

from app.db.session import SessionLocal

from app.services.procurement.policy_service import PolicyService

from app.services.procurement.supplier_service import SupplierService


def main():

    print("\n======================================")
    print(" CANTILL SUPPLIER SERVICE TEST")
    print("======================================")

    db = SessionLocal()

    try:

        # -----------------------------------------
        # 1. LOAD DATASETS
        # -----------------------------------------

        print("\nLoading procurement datasets...")

        supplier_master = pd.read_csv(
            "data/source/master_data/supplier_master.csv"
        )

        po_history = pd.read_csv(
            "data/source/master_data/po_history.csv"
        )

        contract_register = pd.read_csv(
            "data/source/contracts/contract_register.csv"
        )

        item_master = pd.read_csv(
            "data/source/master_data/item_master.csv"
        )

        print("Supplier records:", len(supplier_master))
        print("Purchase records:", len(po_history))
        print("Contract records:", len(contract_register))
        print("Item records:", len(item_master))

        # -----------------------------------------
        # 2. LOAD ACTIVE PROCUREMENT POLICY
        # -----------------------------------------

        print("\nLoading active procurement policy...")

        policy_service = PolicyService(db)

        active_policy = policy_service.get_active_policy()

        ranking_weights = (
            policy_service.get_supplier_ranking_weights()
        )

        print("Policy version:", active_policy["version"])
        print("Effective date:", active_policy["effective_date"])

        print("\nRanking weights:")

        for factor, weight in ranking_weights.items():
            print(f"{factor}: {weight:.0%}")

        print(
            "Total:",
            f"{sum(ranking_weights.values()):.0%}"
        )

        # -----------------------------------------
        # 3. INITIALIZE SUPPLIER SERVICE
        # -----------------------------------------

        print("\nInitializing SupplierService...")

        service = SupplierService(
            supplier_master=supplier_master,
            po_history=po_history,
            contract_register=contract_register,
            item_master=item_master,
            ranking_weights=ranking_weights
        )

        print("SupplierService initialized successfully.")

        # -----------------------------------------
        # 4. GET ELIGIBLE SUPPLIERS
        # -----------------------------------------

        category = "Bearings & Transmission"

        calculation_date = "2026-11-18"

        print("\nCategory:", category)
        print("Calculation date:", calculation_date)

        eligible_suppliers = service.get_eligible_suppliers(
            category=category,
            calculation_date=calculation_date
        )

        print("\nELIGIBLE SUPPLIERS")
        print("--------------------------------------")

        if eligible_suppliers.empty:

            print("No eligible suppliers found.")

            return

        print(
            eligible_suppliers[
                [
                    "supplier_id",
                    "name",
                    "status",
                    "categories",
                    "on_time_pct",
                    "quality_rating"
                ]
            ].to_string(index=False)
        )

        print(
            "\nTotal eligible suppliers:",
            len(eligible_suppliers)
        )

        # -----------------------------------------
        # 5. RANK ELIGIBLE SUPPLIERS
        # -----------------------------------------

        print("\nRANKING SUPPLIERS...")

        ranked_suppliers = service.rank_suppliers(
            eligible_suppliers=eligible_suppliers,
            calculation_date=calculation_date,
            category=category
        )

        print("\nFINAL SUPPLIER RANKING")
        print("======================================")

        display_columns = [
            "supplier_rank",
            "supplier_id",
            "name",
            "purchase_frequency",
            "purchase_recency_days",
            "contract_count",
            "purchase_frequency_score",
            "recency_score",
            "contract_history_score",
            "delivery_score",
            "quality_score",
            "ranking_score"
        ]

        print(
            ranked_suppliers[display_columns].to_string(
                index=False,
                formatters={
                    "purchase_frequency_score": "{:.3f}".format,
                    "recency_score": "{:.3f}".format,
                    "contract_history_score": "{:.3f}".format,
                    "delivery_score": "{:.3f}".format,
                    "quality_score": "{:.3f}".format,
                    "ranking_score": "{:.4f}".format
                }
            )
        )

        # -----------------------------------------
        # 6. VERIFY POLICY WEIGHTS
        # -----------------------------------------

        print("\nPOLICY VALIDATION")
        print("--------------------------------------")

        assert abs(sum(ranking_weights.values()) - 1.0) < 0.000001

        assert (
            set(ranking_weights.keys())
            == SupplierService.REQUIRED_WEIGHT_FACTORS
        )

        print("All ranking weights are valid.")
        print("Total ranking weight is 100%.")

        # -----------------------------------------
        # 7. VERIFY SUPPLIER STATUS
        # -----------------------------------------

        invalid_suppliers = ranked_suppliers[
            ~ranked_suppliers["status"]
            .astype(str)
            .str.upper()
            .eq("ACTIVE")
        ]

        assert invalid_suppliers.empty

        print("No blocked or inactive suppliers ranked.")

        print("\n======================================")
        print(" SUPPLIER SERVICE TEST PASSED")
        print("======================================")

    except Exception as error:

        print("\nSUPPLIER SERVICE TEST FAILED")
        print("Error:", error)

        raise

    finally:

        db.close()


if __name__ == "__main__":
    main()
