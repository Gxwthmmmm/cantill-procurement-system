
import pandas as pd

from app.db.session import SessionLocal

from app.services.procurement.policy_service import PolicyService
from app.services.procurement.supplier_service import SupplierService
from app.services.procurement.recommendation_service import (
    SupplierRecommendationService
)


def main():

    print("\n==========================================")
    print(" CANTILL SUPPLIER RECOMMENDATION TEST")
    print("==========================================")

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

        item_master = pd.read_csv(
            "data/source/master_data/item_master.csv"
        )

        contract_register = pd.read_csv(
            "data/source/contracts/contract_register.csv"
        )

        contract_lines = pd.read_csv(
            "data/source/contracts/contract_lines.csv"
        )

        print("Suppliers:", len(supplier_master))
        print("Purchase records:", len(po_history))
        print("Items:", len(item_master))
        print("Contracts:", len(contract_register))
        print("Contract lines:", len(contract_lines))

        # -----------------------------------------
        # 2. LOAD ACTIVE POLICY
        # -----------------------------------------

        print("\nLoading active procurement policy...")

        policy_service = PolicyService(db)

        active_policy = policy_service.get_active_policy()

        ranking_weights = (
            policy_service.get_supplier_ranking_weights()
        )

        print("Policy version:", active_policy["version"])

        # -----------------------------------------
        # 3. INITIALIZE SUPPLIER SERVICE
        # -----------------------------------------

        supplier_service = SupplierService(
            supplier_master=supplier_master,
            po_history=po_history,
            contract_register=contract_register,
            item_master=item_master,
            ranking_weights=ranking_weights
        )

        # -----------------------------------------
        # 4. INITIALIZE RECOMMENDATION SERVICE
        # -----------------------------------------

        recommendation_service = SupplierRecommendationService(
            supplier_service=supplier_service,
            supplier_master=supplier_master,
            po_history=po_history,
            contract_lines=contract_lines,
            contract_register=contract_register,
            item_master=item_master
        )

        print("Recommendation service initialized.")

        # -----------------------------------------
        # 5. SELECT A REAL ITEM AND CATEGORY
        # -----------------------------------------

        valid_items = item_master[
            item_master["item_code"].notna()
            & item_master["category"].notna()
        ].copy()

        if valid_items.empty:
            raise ValueError("No valid item/category combinations found.")

        selected_item = valid_items.iloc[0]

        item_code = selected_item["item_code"]
        category = selected_item["category"]

        calculation_date = "2026-11-18"

        print("\nTEST ITEM")
        print("------------------------------------------")
        print("Item code:", item_code)
        print("Description:", selected_item["description"])
        print("Category:", category)
        print("Calculation date:", calculation_date)

        # -----------------------------------------
        # 6. TEST RFQ - 3 SUPPLIER RECOMMENDATIONS
        # -----------------------------------------

        print("\n==========================================")
        print(" RFQ TEST - TOP 3 SUPPLIERS")
        print("==========================================")

        rfq_result = recommendation_service.recommend_suppliers(
            item_code=item_code,
            category=category,
            calculation_date=calculation_date,
            supplier_count=3
        )

        print("Status:", rfq_result["status"])

        print(
            "Requested:",
            rfq_result["supplier_count_requested"]
        )

        print(
            "Returned:",
            rfq_result["supplier_count_returned"]
        )

        for supplier in rfq_result["suppliers"]:

            print("\nRank:", supplier["supplier_rank"])
            print("Supplier:", supplier["supplier_name"])
            print("Supplier ID:", supplier["supplier_id"])
            print("Recommendation:", supplier["recommendation_source"])
            print("Reference price:", supplier["reference_price"])
            print("Price source:", supplier["price_source"])

        # -----------------------------------------
        # 7. TEST RFP - 5 SUPPLIER RECOMMENDATIONS
        # -----------------------------------------

        print("\n==========================================")
        print(" RFP TEST - TOP 5 SUPPLIERS")
        print("==========================================")

        rfp_result = recommendation_service.recommend_suppliers(
            item_code=item_code,
            category=category,
            calculation_date=calculation_date,
            supplier_count=5
        )

        print("Status:", rfp_result["status"])

        print(
            "Requested:",
            rfp_result["supplier_count_requested"]
        )

        print(
            "Returned:",
            rfp_result["supplier_count_returned"]
        )

        for supplier in rfp_result["suppliers"]:

            print("\nRank:", supplier["supplier_rank"])
            print("Supplier:", supplier["supplier_name"])
            print("Supplier ID:", supplier["supplier_id"])
            print("Recommendation:", supplier["recommendation_source"])
            print("Reference price:", supplier["reference_price"])
            print("Price source:", supplier["price_source"])

        # -----------------------------------------
        # 8. TEST NEW ITEM - NO SUPPLIER SUGGESTIONS
        # -----------------------------------------

        print("\n==========================================")
        print(" NEW ITEM TEST")
        print("==========================================")

        new_item_result = recommendation_service.recommend_suppliers(
            item_code=None,
            category=category,
            calculation_date=calculation_date,
            supplier_count=3,
            is_new_item=True
        )

        print("Status:", new_item_result["status"])
        print("Suppliers returned:", new_item_result["supplier_count_returned"])

        assert new_item_result["supplier_count_returned"] == 0

        # -----------------------------------------
        # 9. VALIDATE RECOMMENDATIONS
        # -----------------------------------------

        print("\n==========================================")
        print(" VALIDATION")
        print("==========================================")

        for result in [rfq_result, rfp_result]:

            supplier_ids = [
                supplier["supplier_id"]
                for supplier in result["suppliers"]
            ]

            assert len(supplier_ids) == len(set(supplier_ids)), (
                "Duplicate suppliers found."
            )

            for supplier in result["suppliers"]:
                assert supplier["supplier_id"] in set(
                    supplier_master.loc[
                        supplier_master["status"]
                        .astype(str)
                        .str.upper()
                        .eq("ACTIVE"),
                        "supplier_id"
                    ]
                ), "Inactive or blocked supplier was recommended."

        print("No duplicate suppliers.")
        print("No inactive or blocked suppliers.")
        print("New items receive no supplier suggestions.")

        print("\n==========================================")
        print(" RECOMMENDATION TEST COMPLETED")
        print("==========================================")

    except Exception as error:

        print("\nRECOMMENDATION TEST FAILED")
        print("Error:", error)

        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()

