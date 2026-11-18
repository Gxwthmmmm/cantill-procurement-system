
from pathlib import Path
import sys

import pandas as pd

# =============================================
# PROJECT CONFIGURATION
# =============================================

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.services.procurement.contract_service import (
    ContractAllocationService
)
from app.services.procurement.policy_service import PolicyService


# =============================================
# DATASET PATHS
# =============================================

DATA_DIR = BACKEND_DIR / "data" / "source"

CONTRACT_LINES_PATH = (
    DATA_DIR / "contracts" / "contract_lines.csv"
)

CONTRACT_REGISTER_PATH = (
    DATA_DIR / "contracts" / "contract_register.csv"
)

SUPPLIER_MASTER_PATH = (
    DATA_DIR / "master_data" / "supplier_master.csv"
)

PR_BATCH_PATH = (
    DATA_DIR / "pr_batches" / "sample_pr_batch.csv"
)


# =============================================
# 1. LOAD DATASETS
# =============================================

print("\n==========================================")
print("LOADING PROCUREMENT DATASETS")
print("==========================================")

contract_lines = pd.read_csv(CONTRACT_LINES_PATH)
contract_register = pd.read_csv(CONTRACT_REGISTER_PATH)
supplier_master = pd.read_csv(SUPPLIER_MASTER_PATH)
pr_batch = pd.read_csv(PR_BATCH_PATH)

print(f"Contract lines: {len(contract_lines)}")
print(f"Contract register: {len(contract_register)}")
print(f"Supplier master: {len(supplier_master)}")
print(f"PR batch lines: {len(pr_batch)}")


# =============================================
# 2. LOAD ACTIVE POLICY FROM DATABASE
# =============================================

print("\n==========================================")
print("LOADING ACTIVE PROCUREMENT POLICY")
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
# 3. PREPARE REQUIREMENTS
# =============================================

print("\n==========================================")
print("PREPARING REQUIREMENTS")
print("==========================================")

required_columns = {
    "pr_no",
    "item_code",
    "quantity",
    "created_at",
}

missing_columns = required_columns - set(pr_batch.columns)

if missing_columns:
    raise ValueError(
        f"Missing columns in sample PR batch: {sorted(missing_columns)}"
    )

pr_batch["created_at"] = pd.to_datetime(
    pr_batch["created_at"],
    errors="coerce"
)

pr_batch["quantity"] = pd.to_numeric(
    pr_batch["quantity"],
    errors="coerce"
)

requirements = pr_batch.rename(
    columns={
        "pr_no": "requirement_id",
        "quantity": "total_quantity",
    }
)[
    [
        "requirement_id",
        "item_code",
        "total_quantity",
        "created_at",
    ]
].copy()

# Make each PR line unique, even when multiple lines
# belong to the same purchase requisition.
line_numbers = (
    requirements.groupby("requirement_id")
    .cumcount()
    .add(1)
)

requirements["requirement_id"] = (
    requirements["requirement_id"].astype(str)
    + "-"
    + line_numbers.astype(str)
)

# Exclude rows with invalid dates or quantities.
requirements = requirements.dropna(
    subset=["created_at", "total_quantity"]
)

requirements = requirements[
    requirements["total_quantity"] > 0
].copy()

requirements = requirements.reset_index(drop=True)

print("Valid requirements prepared:", len(requirements))


# =============================================
# 4. INITIALIZE CONTRACT ALLOCATION SERVICE
# =============================================

print("\n==========================================")
print("INITIALIZING CONTRACT SERVICE")
print("==========================================")

service = ContractAllocationService(
    contract_lines=contract_lines,
    contract_register=contract_register,
    supplier_master=supplier_master,
    policy_data=policy_data,
)

print("Contract allocation service initialized.")


# =============================================
# 5. RUN CONTRACT ALLOCATION
# =============================================

print("\n==========================================")
print("RUNNING CONTRACT ALLOCATION")
print("==========================================")

results = service.allocate_requirements(
    requirements
)

print("Allocation process completed.")


# =============================================
# 6. ALLOCATION STATUS SUMMARY
# =============================================

print("\n==========================================")
print("ALLOCATION STATUS SUMMARY")
print("==========================================")

status_summary = (
    results["allocation_status"]
    .value_counts(dropna=False)
)

print(status_summary.to_string())

print("\nTotal processed:", len(results))

allocated_count = (
    results["allocation_status"] == "ALLOCATED"
).sum()

print("Successfully allocated:", allocated_count)

print(
    "Not allocated:",
    len(results) - allocated_count
)


# =============================================
# 7. SAMPLE ALLOCATION RESULTS
# =============================================

print("\n==========================================")
print("SAMPLE ALLOCATION RESULTS")
print("==========================================")

print(
    results.head(15).to_string(index=False)
)


# =============================================
# 8. CONTRACT BALANCE SUMMARY
# =============================================

print("\n==========================================")
print("CONTRACT BALANCE SUMMARY")
print("==========================================")

balances = service.get_contract_balance_summary()

print(
    balances.to_string(index=False)
)


# =============================================
# 9. VALIDATION CHECKS
# =============================================

print("\n==========================================")
print("VALIDATION CHECKS")
print("==========================================")

allocated = results[
    results["allocation_status"] == "ALLOCATED"
].copy()


# CHECK 1: Only active suppliers are allocated.

invalid_allocations = allocated[
    ~allocated["supplier_id"].isin(
        service.active_supplier_ids
    )
]

assert invalid_allocations.empty, (
    "Blocked or inactive supplier received an allocation."
)

print("PASS: Only active suppliers received allocations.")


# CHECK 2: No contract exceeds its ceiling.

assert (
    service.contract_balances["remaining_value"] >= -0.000001
).all(), (
    "A contract exceeded its available ceiling."
)

print("PASS: No contract exceeded its available ceiling.")


# CHECK 3: Allocation values are correct.

requirement_lookup = requirements.set_index(
    "requirement_id"
)

for _, allocation in allocated.iterrows():

    requirement = requirement_lookup.loc[
        allocation["requirement_id"]
    ]

    expected_value = (
        float(requirement["total_quantity"])
        * float(allocation["contract_rate"])
    )

    actual_value = float(
        allocation["allocated_value"]
    )

    assert abs(expected_value - actual_value) < 0.01, (
        "Allocation value calculation mismatch."
    )

print("PASS: Allocation values are calculated correctly.")


# CHECK 4: Every successful allocation has a contract ID.

assert allocated["contract_id"].notna().all(), (
    "Successful allocation is missing a contract ID."
)

print("PASS: Every successful allocation has a contract ID.")


# CHECK 5: Allocated supplier and contract are consistent.

contract_supplier_lookup = (
    contract_register.set_index("contract_id")["supplier_id"]
)

for _, allocation in allocated.iterrows():

    expected_supplier = contract_supplier_lookup.loc[
        allocation["contract_id"]
    ]

    assert allocation["supplier_id"] == expected_supplier, (
        "Allocated supplier does not match the contract register."
    )

print("PASS: Allocated suppliers match their contracts.")


# =============================================
# 10. SAVE TEST RESULTS
# =============================================

OUTPUT_DIR = BACKEND_DIR / "data" / "processed"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RESULT_PATH = OUTPUT_DIR / "contract_allocation_test_results.csv"

results.to_csv(
    RESULT_PATH,
    index=False
)

BALANCE_PATH = OUTPUT_DIR / "contract_balance_test_results.csv"

balances.to_csv(
    BALANCE_PATH,
    index=False
)

print("\nResults saved:")
print(RESULT_PATH)
print(BALANCE_PATH)


# =============================================
# FINAL RESULT
# =============================================

print("\n==========================================")
print("CONTRACT ALLOCATION TEST COMPLETED")
print("==========================================")

print("All validation checks passed.")
