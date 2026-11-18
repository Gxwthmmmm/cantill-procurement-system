
from pathlib import Path
import pandas as pd

from app.services.procurement.valuation import ProcurementValuator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_csv(filename):
    matches = list(DATA_DIR.rglob(filename))

    if not matches:
        raise FileNotFoundError(filename)

    return pd.read_csv(matches[0])


contract_lines = load_csv("contract_lines.csv")
contract_register = load_csv("contract_register.csv")
po_history = load_csv("po_history.csv")
item_master = load_csv("item_master.csv")

valuator = ProcurementValuator(
    contract_lines,
    contract_register,
    po_history,
    item_master
)

test_cases = [
    {
        "name": "Existing item",
        "item_code": "ITM-1024",
        "quantity": 10,
        "estimated_unit_price": None
    },
    {
        "name": "New item with estimated price",
        "item_code": None,
        "quantity": 5,
        "estimated_unit_price": 1500
    },
    {
        "name": "New item without estimated price",
        "item_code": None,
        "quantity": 5,
        "estimated_unit_price": None
    }
]

for test in test_cases:
    print(f"\n{test['name']}")

    result = valuator.value_request(
        item_code=test["item_code"],
        quantity=test["quantity"],
        calculation_date="2026-11-18",
        estimated_unit_price=test["estimated_unit_price"]
    )

    print(result)
