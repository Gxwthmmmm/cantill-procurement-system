
from pathlib import Path
import pandas as pd

from app.services.procurement.validation import ProcurementValidator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_csv(filename):
    matches = list(DATA_DIR.rglob(filename))

    if not matches:
        raise FileNotFoundError(filename)

    return pd.read_csv(matches[0])


items = load_csv("item_master.csv")
plants = load_csv("plants.csv")

validator = ProcurementValidator(items, plants)

test_requests = [
    {"plant": "PUN1", "item_code": "ITM-1024"},
    {"plant": "PUN2", "item_code": "ITM-1024"},
    {"plant": "CHK1", "item_code": None},
    {"plant": "CHK1", "item_code": "INVALID-001"}
]

for index, request in enumerate(test_requests, start=1):
    print(f"\nTEST {index}")
    print("Request:", request)
    print("Result:", validator.validate_request(request))
