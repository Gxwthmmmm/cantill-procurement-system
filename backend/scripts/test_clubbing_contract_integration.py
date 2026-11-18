
from pathlib import Path
import sys

import pandas as pd

# =============================================
# PROJECT CONFIGURATION
# =============================================

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.services.procurement.policy_service import PolicyService
from app.services.procurement.clubbing_service import (
    RequirementClubbingService
)
from app.services.procurement.contract_service import (
    ContractAllocationService
)


# =============================================
# DATASET PATHS
# =============================================

DATA_DIR = BACKEND_DIR / "data" / "source"
OUTPUT_DIR = BACKEND_DIR / "data" / "processed"

PR_BATCH_PATH = (
    DATA_DIR / "pr_batches" / "sample_pr_batch.csv"
)

CONTRACT_LINES_PATH = (
    DATA_DIR / "contracts" / "contract_lines.csv"
)

CONTRACT_REGISTER_PATH = (
    DATA_DIR / "contracts" / "contract_register.csv"
)

SUPPLIER_MASTER_PATH = (
    DATA_DIR / "master_data" / "supplier_master.csv"
)


# =============================================
# 1. LOAD DATASETS
# =============================================

print("\n==========================================")
print("LOADING PROCUREMENT DATASETS")
print("==========================================")

pr_batch = pd.read_csv(PR_BATCH_PATH)

contract_lines = pd.read_csv(CONTRACT_LINES_PATH)

contract_register = pd.read_csv(CONTRACT_REGISTER_PATH)

supplier_master = pd.read_csv(SUPPLIER_MASTER_PATH)

print("Original PR lines:", len(pr_batch))
print("Contract lines:", len(contract_lines))
print("Contract register:", len(contract_register))
print("Suppliers:", len(supplier_master))


# =============================================
# 2. LOAD ACTIVE POLICY
# =============================================

print("\n==========================================")
print("LOADING ACTIVE POLICY")
print("==========================================")

db = SessionLocal()

try:
    active_policy = PolicyService(db).get_active_policy()
finally:
    db.close()

policy_data = active_policy["policy_data"]

print("Policy version:", active_policy["version"])
print("Effective date:", active_policy["effective_date"])


# =============================================
# 3. VALIDATE BASIC PR DATA
# =============================================

print("\n==========================================")
print("PREPARING PR DATA")
print("==========================================")

required_columns = {
    "pr_no",
    "pr_line",
    "created_at",
    "plant",
    "item_code",
    "need_by_date",
    "quantity",
    "urgency",
}

missing_columns = required_columns - set(pr_batch.columns)

if missing_columns:
    raise ValueError(
        f"Missing PR columns: {sorted(missing_columns)}"
    )

pr_batch["created_at"] = pd.to_datetime(
    pr_batch["created_at"],
    errors="coerce"
)

pr_batch["need_by_date"] = pd.to_datetime(
    pr_batch["need_by_date"],
    errors="coerce"
)

pr_batch["quantity"] = pd.to_numeric(
    pr_batch["quantity"],
    errors="coerce"
)

# Preserve invalid rows separately rather than silently
# passing invalid dates or quantities to the clubbing service.
valid_mask = (
    pr_batch["created_at"].notna()
    & pr_batch["need_by_date"].notna()
    & pr_batch["pr_no"].notna()
    & pr_batch["pr_line"].notna()
    & pr_batch["quantity"].notna()
    & (pr_batch["quantity"] > 0)
)

valid_requests = pr_batch.loc[valid_mask].copy()
invalid_requests = pr_batch.loc[~valid_mask].copy()

print("Valid PR lines:", len(valid_requests))
print("Invalid PR lines:", len(invalid_requests))


# =============================================
# 4. RUN REQUIREMENT CLUBBING
# =============================================

print("\n==========================================")
print("RUNNING REQUIREMENT CLUBBING")
print("==========================================")

clubbing_service = RequirementClubbingService(
    policy_data=policy_data
)

clubbed_requests = clubbing_service.club_requirements(
    valid_requests
)

requirement_summary = (
    clubbing_service.get_requirement_summary(
        clubbed_requests
    )
)

print("Original valid PR lines:", len(valid_requests))
print("Consolidated requirements:", len(requirement_summary))

print(
    "PR lines belonging to multi-line requirements:",
    int(
        clubbed_requests.loc[
            clubbed_requests["requirement_line_count"] > 1
        ].shape[0]
    )
)

print(
    "Net lines consolidated:",
    len(valid_requests) - len(requirement_summary)
)


# =============================================
# 5. PREPARE REQUIREMENTS FOR ALLOCATION
# =============================================

print("\n==========================================")
print("PREPARING CONSOLIDATED REQUIREMENTS")
print("==========================================")

allocation_requirements = requirement_summary.rename(
    columns={
        "created_at": "created_at",
    }
)[
    [
        "requirement_id",
        "item_code",
        "total_quantity",
        "created_at",
    ]
].copy()

allocation_requirements["created_at"] = pd.to_datetime(
    allocation_requirements["created_at"],
    errors="coerce"
)

allocation_requirements["total_quantity"] = pd.to_numeric(
    allocation_requirements["total_quantity"],
    errors="coerce"
)

allocation_requirements = allocation_requirements.dropna(
    subset=["created_at", "total_quantity"]
)

allocation_requirements = allocation_requirements[
    allocation_requirements["total_quantity"] > 0
].copy()

print(
    "Requirements ready for contract allocation:",
    len(allocation_requirements)
)


# =============================================
# 6. INITIALIZE CONTRACT ALLOCATION SERVICE
# =============================================

print("\n==========================================")
print("INITIALIZING CONTRACT SERVICE")
print("==========================================")

contract_service = ContractAllocationService(
    contract_lines=contract_lines,
    contract_register=contract_register,
    supplier_master=supplier_master,
    policy_data=policy_data,
)

print("Contract service initialized.")


# =============================================
# 7. ALLOCATE CONSOLIDATED REQUIREMENTS
# =============================================

print("\n==========================================")
print("ALLOCATING CONSOLIDATED REQUIREMENTS")
print("==========================================")

allocation_results = contract_service.allocate_requirements(
    allocation_requirements
)

print("Allocation completed.")


# =============================================
# 8. COMBINE REQUIREMENT AND ALLOCATION RESULTS
# =============================================

print("\n==========================================")
print("BUILDING FINAL REQUIREMENT RESULTS")
print("==========================================")

final_requirements = requirement_summary.merge(
    allocation_results,
    on="requirement_id",
    how="left",
    validate="one_to_one",
)

print("Final requirement records:", len(final_requirements))


# =============================================
# 9. MAP RESULTS BACK TO ORIGINAL PR LINES
# =============================================

print("\n==========================================")
print("MAPPING RESULTS TO PR LINES")
print("==========================================")

line_results = clubbed_requests.merge(
    allocation_results,
    on="requirement_id",
    how="left",
    validate="many_to_one",
)

print("PR lines with requirement results:", len(line_results))

# Preserve invalid PR lines for review.
if not invalid_requests.empty:

    invalid_requests = invalid_requests.copy()

    invalid_requests["requirement_id"] = None
    invalid_requests["allocation_status"] = "INVALID_PR_DATA"
    invalid_requests["contract_id"] = None
    invalid_requests["supplier_id"] = None
    invalid_requests["contract_rate"] = None
    invalid_requests["allocated_value"] = None
    invalid_requests["remaining_value"] = None
    invalid_requests["reason"] = (
        "PR line contains missing or invalid required data."
    )

    # Align columns before concatenation.
    all_columns = list(
        dict.fromkeys(
            list(line_results.columns)
            + list(invalid_requests.columns)
        )
    )

    line_results = line_results.reindex(
        columns=all_columns
    )

    invalid_requests = invalid_requests.reindex(
        columns=all_columns
    )

    line_results = pd.concat(
        [line_results, invalid_requests],
        ignore_index=True,
    )

print("Total PR lines retained:", len(line_results))


# =============================================
# 10. ALLOCATION SUMMARY
# =============================================

print("\n==========================================")
print("ALLOCATION STATUS SUMMARY")
print("==========================================")

print(
    allocation_results["allocation_status"]
    .value_counts(dropna=False)
    .to_string()
)

print("\nTotal consolidated requirements:")
print(len(allocation_results))

print(
    "\nSuccessfully allocated:",
    int(
        (
            allocation_results["allocation_status"]
            == "ALLOCATED"
        ).sum()
    )
)


# =============================================
# 11. CONTRACT BALANCE SUMMARY
# =============================================

print("\n==========================================")
print("CONTRACT BALANCE SUMMARY")
print("==========================================")

balances = contract_service.get_contract_balance_summary()

print(balances.to_string(index=False))


# =============================================
# 12. VALIDATION CHECKS
# =============================================

print("\n==========================================")
print("INTEGRATION VALIDATION CHECKS")
print("==========================================")

# Check 1: Every valid PR line has a requirement ID.

assert clubbed_requests["requirement_id"].notna().all()

print("PASS: Every valid PR line has a requirement ID.")


# Check 2: Requirement IDs are consistent.

assert (
    line_results.loc[
        line_results["requirement_id"].notna(),
        "requirement_id"
    ].isin(requirement_summary["requirement_id"])
).all()

print("PASS: PR lines map to valid consolidated requirements.")


# Check 3: No requirement is allocated more than once.

assert allocation_results["requirement_id"].is_unique

print("PASS: Each consolidated requirement is allocated once.")


# Check 4: Only active suppliers receive allocations.

allocated = allocation_results[
    allocation_results["allocation_status"] == "ALLOCATED"
]

invalid_supplier_allocations = allocated[
    ~allocated["supplier_id"].isin(
        contract_service.active_supplier_ids
    )
]

assert invalid_supplier_allocations.empty

print("PASS: Only active suppliers received allocations.")


# Check 5: Contract ceilings are respected.

assert (
    contract_service.contract_balances["remaining_value"]
    >= -0.000001
).all()

print("PASS: Contract ceilings are respected.")


# Check 6: No new item receives an existing contract.

new_item_allocations = final_requirements[
    final_requirements["is_new_item"]
    & (
        final_requirements["allocation_status"]
        == "ALLOCATED"
    )
]

assert new_item_allocations.empty

print("PASS: New items are not allocated existing contracts.")


# Check 7: Original valid PR lines are preserved.

assert len(clubbed_requests) == len(valid_requests)

print("PASS: No valid PR lines were lost during clubbing.")


# Check 8: Consolidated quantities match source PR quantities.

source_quantities = (
    clubbed_requests
    .groupby("requirement_id")["quantity"]
    .sum()
    .sort_index()
)

summary_quantities = (
    requirement_summary
    .set_index("requirement_id")["total_quantity"]
    .sort_index()
)

pd.testing.assert_series_equal(
    source_quantities,
    summary_quantities,
    check_names=False,
    check_dtype=False,
    check_exact=False,
    atol=0.000001,
    rtol=0,
)

print("PASS: Consolidated quantities match original PR lines.")


# =============================================
# 13. SAVE OUTPUT FILES
# =============================================

print("\n==========================================")
print("SAVING INTEGRATION OUTPUTS")
print("==========================================")

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

clubbed_path = (
    OUTPUT_DIR / "clubbed_pr_requirements.csv"
)

summary_path = (
    OUTPUT_DIR / "consolidated_requirement_summary.csv"
)

allocation_path = (
    OUTPUT_DIR / "consolidated_contract_allocations.csv"
)

final_path = (
    OUTPUT_DIR / "final_pr_line_allocation_results.csv"
)

balance_path = (
    OUTPUT_DIR / "integrated_contract_balances.csv"
)

clubbed_requests.to_csv(
    clubbed_path,
    index=False
)

requirement_summary.to_csv(
    summary_path,
    index=False
)

allocation_results.to_csv(
    allocation_path,
    index=False
)

line_results.to_csv(
    final_path,
    index=False
)

balances.to_csv(
    balance_path,
    index=False
)

print("Saved:", clubbed_path)
print("Saved:", summary_path)
print("Saved:", allocation_path)
print("Saved:", final_path)
print("Saved:", balance_path)


# =============================================
# FINAL RESULT
# =============================================

print("\n==========================================")
print("CLUBBING + CONTRACT ALLOCATION COMPLETED")
print("==========================================")

print("Original PR lines:", len(pr_batch))
print("Valid PR lines:", len(valid_requests))
print("Invalid PR lines:", len(invalid_requests))
print("Consolidated requirements:", len(requirement_summary))
print("Contract allocations:", len(allocated))

print("\nAll integration validation checks passed.")
