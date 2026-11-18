
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_csv(filename):
    matches = list(DATA_DIR.rglob(filename))

    if not matches:
        raise FileNotFoundError(f"{filename} not found")

    return pd.read_csv(matches[0])


# Load datasets
items = load_csv("item_master.csv")
suppliers = load_csv("supplier_master.csv")
plants = load_csv("plants.csv")
po_history = load_csv("po_history.csv")
contract_register = load_csv("contract_register.csv")
contract_lines = load_csv("contract_lines.csv")
prs = load_csv("sample_pr_batch.csv")


def check_reference(label, source, column, master, master_column):
    source_values = set(source[column].dropna().astype(str))
    master_values = set(master[master_column].dropna().astype(str))

    missing = source_values - master_values

    print(f"\n{label}")
    print(f"Unique references: {len(source_values)}")
    print(f"Unmatched references: {len(missing)}")

    if missing:
        print("Unmatched values:", sorted(missing))
    else:
        print("All references matched.")


print("=" * 65)
print("CANTILL PROCUREMENT - RELATIONSHIP VALIDATION")
print("=" * 65)

# Item references
check_reference(
    "PO -> ITEM MASTER",
    po_history, "item_code",
    items, "item_code"
)

check_reference(
    "CONTRACT LINES -> ITEM MASTER",
    contract_lines, "item_code",
    items, "item_code"
)

check_reference(
    "PR -> ITEM MASTER",
    prs, "item_code",
    items, "item_code"
)

# Supplier references
check_reference(
    "PO -> SUPPLIER MASTER",
    po_history, "supplier_id",
    suppliers, "supplier_id"
)

check_reference(
    "CONTRACT REGISTER -> SUPPLIER MASTER",
    contract_register, "supplier_id",
    suppliers, "supplier_id"
)

# Contract references
check_reference(
    "CONTRACT LINES -> CONTRACT REGISTER",
    contract_lines, "contract_id",
    contract_register, "contract_id"
)

# Plant references
check_reference(
    "PO -> PLANT MASTER",
    po_history, "plant",
    plants, "plant"
)

check_reference(
    "PR -> PLANT MASTER",
    prs, "plant",
    plants, "plant"
)

# Contract ceiling validation
print("\nCONTRACT CEILING CHECK")

contract_register["remaining_value"] = (
    contract_register["value_cap"]
    - contract_register["consumed_value"]
)

print(
    contract_register[
        ["contract_id", "value_cap",
         "consumed_value", "remaining_value"]
    ].to_string(index=False)
)

overused = contract_register[
    contract_register["consumed_value"]
    > contract_register["value_cap"]
]

print(f"\nContracts exceeding ceiling: {len(overused)}")

print("\n" + "=" * 65)
print("RELATIONSHIP VALIDATION COMPLETED")
print("=" * 65)
