
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_csv(filename):
    matches = list(DATA_DIR.rglob(filename))
    if not matches:
        raise FileNotFoundError(filename)
    return pd.read_csv(matches[0])

prs = load_csv("sample_pr_batch.csv")
items = load_csv("item_master.csv")
contracts = load_csv("contract_register.csv")

print("=" * 65)
print("CANTILL PROCUREMENT - EXCEPTION INVESTIGATION")
print("=" * 65)

# 1. Invalid plant references
valid_plants = {"PUN1", "CHK1"}

invalid_plant_prs = prs[
    ~prs["plant"].isin(valid_plants)
]

print("\n1. INVALID PLANT REQUESTS")
print("Affected rows:", len(invalid_plant_prs))

if not invalid_plant_prs.empty:
    print(
        invalid_plant_prs[
            ["pr_no", "pr_line", "plant",
             "description", "requester"]
        ].to_string(index=False)
    )

# 2. Missing item codes
missing_codes = prs[prs["item_code"].isna()]

print("\n2. MISSING ITEM CODES")
print("Affected rows:", len(missing_codes))

print(
    missing_codes[
        ["pr_no", "pr_line", "description",
         "quantity", "uom"]
    ].to_string(index=False)
)

# 3. Missing estimated prices
missing_prices = prs[
    prs["estimated_unit_price"].isna()
]

print("\n3. MISSING ESTIMATED PRICES")
print("Affected rows:", len(missing_prices))

print(
    missing_prices[
        ["pr_no", "pr_line", "item_code",
         "description", "quantity"]
    ].to_string(index=False)
)

# 4. Contract ceiling checks
contracts["remaining_value"] = (
    contracts["value_cap"]
    - contracts["consumed_value"]
)

print("\n4. CONTRACT CEILING STATUS")

for _, contract in contracts.iterrows():
    status = (
        "EXCEEDED"
        if contract["remaining_value"] < 0
        else "WITHIN CEILING"
    )

    print(
        contract["contract_id"],
        "| Remaining:",
        contract["remaining_value"],
        "|",
        status
    )

print("\n" + "=" * 65)
print("INVESTIGATION COMPLETED")
print("=" * 65)
