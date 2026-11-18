
import pandas as pd

from app.db.session import SessionLocal

from app.services.procurement.policy_service import PolicyService
from app.services.procurement.clubbing_service import (
    RequirementClubbingService
)


def main():

    print("\n==========================================")
    print(" CANTILL REQUIREMENT CLUBBING TEST")
    print("==========================================")

    db = SessionLocal()

    try:

        # 1. LOAD SAMPLE PURCHASE REQUESTS
        print("\nLoading sample purchase requests...")

        requests = pd.read_csv(
            "data/source/pr_batches/sample_pr_batch.csv"
        )

        print("Total PR lines:", len(requests))

        # 2. LOAD ACTIVE PROCUREMENT POLICY
        print("\nLoading active procurement policy...")

        policy_service = PolicyService(db)

        active_policy = policy_service.get_active_policy()

        print("Policy version:", active_policy["version"])
        print("Effective date:", active_policy["effective_date"])

        # 3. INITIALIZE CLUBBING SERVICE
        service = RequirementClubbingService(
            policy_data=active_policy["policy_data"]
        )

        print("\nClubbing service initialized successfully.")

        # 4. CLUB REQUIREMENTS
        print("\nProcessing purchase request lines...")

        clubbed = service.club_requirements(requests)

        summary = service.get_requirement_summary(clubbed)

        print("\nCLUBBING SUMMARY")
        print("------------------------------------------")

        print("Original PR lines:", len(requests))
        print("Generated requirements:", len(summary))
        print(
            "Lines grouped with others:",
            int((clubbed["requirement_line_count"] > 1).sum())
        )
        print(
            "New-item requirements:",
            int(summary["is_new_item"].sum())
        )
        print(
            "Emergency requirements:",
            int(summary["is_emergency"].sum())
        )

        # 5. DISPLAY REQUIREMENT SUMMARY
        print("\nREQUIREMENT DETAILS")
        print("------------------------------------------")

        print(summary.to_string(index=False))

        # 6. VALIDATE SAME ITEM AND PLANT
        print("\nVALIDATING ITEM AND PLANT CONSISTENCY...")

        for requirement_id, group in clubbed.groupby("requirement_id"):

            if bool(group["is_new_item_requirement"].iloc[0]):
                assert len(group) == 1, (
                    "New item lines must never be clubbed."
                )
                continue

            assert group["item_code"].nunique(dropna=False) == 1
            assert group["plant"].nunique(dropna=False) == 1

        print("Item and plant consistency passed.")

        # 7. VALIDATE 14-DAY CREATION WINDOW
        print("\nVALIDATING 14-DAY CREATION WINDOW...")

        for requirement_id, group in clubbed.groupby("requirement_id"):

            first_created = group["requirement_created_at"].iloc[0]

            differences = (
                group["created_at"] - first_created
            ).dt.days

            assert differences.min() >= 0
            assert differences.max() <= 14

        print("14-day creation window passed.")

        # 8. VALIDATE +/- 7-DAY NEED-BY WINDOW
        print("\nVALIDATING +/- 7-DAY NEED-BY WINDOW...")

        for requirement_id, group in clubbed.groupby("requirement_id"):

            if bool(group["is_new_item_requirement"].iloc[0]):
                continue

            first_need_by = (
                group["requirement_need_by_date"].iloc[0]
            )

            differences = (
                group["need_by_date"] - first_need_by
            ).dt.days.abs()

            assert differences.max() <= 7

        print("Need-by date window passed.")

        # 9. VALIDATE EMERGENCY PROPAGATION
        print("\nVALIDATING EMERGENCY PROPAGATION...")

        for requirement_id, group in clubbed.groupby("requirement_id"):

            has_emergency_line = (
                group["urgency"]
                .astype(str)
                .str.casefold()
                .eq("emergency")
                .any()
            )

            requirement_is_emergency = bool(
                group["is_emergency_requirement"].iloc[0]
            )

            assert requirement_is_emergency == has_emergency_line

            if requirement_is_emergency:
                assert group["requirement_urgency"].eq(
                    "Emergency"
                ).all()

        print("Emergency propagation passed.")

        # 10. VALIDATE LINE PRESERVATION
        print("\nVALIDATING LINE PRESERVATION...")

        assert len(clubbed) == len(requests)
        assert clubbed["requirement_id"].notna().all()

        assert not clubbed.duplicated(
            subset=["pr_no", "pr_line"]
        ).any()

        print("All original PR lines are preserved.")
        print("No duplicate PR lines were created.")

        # 11. DISPLAY EXAMPLE CLUBBED REQUIREMENTS
        print("\nEXAMPLE CLUBBED REQUIREMENTS")
        print("------------------------------------------")

        examples = [
            (requirement_id, group)
            for requirement_id, group in clubbed.groupby("requirement_id")
            if len(group) > 1
        ]

        if examples:

            for requirement_id, group in examples[:5]:

                print("\nRequirement:", requirement_id)

                print(
                    group[
                        [
                            "pr_no",
                            "pr_line",
                            "item_code",
                            "plant",
                            "created_at",
                            "need_by_date",
                            "urgency",
                            "requirement_urgency"
                        ]
                    ].to_string(index=False)
                )

        else:
            print("No multi-line requirements found.")

        # 12. FINAL RESULT
        print("\n==========================================")
        print(" CLUBBING TEST PASSED")
        print("==========================================")

    except Exception as error:

        print("\nCLUBBING TEST FAILED")
        print("Error:", error)

        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
