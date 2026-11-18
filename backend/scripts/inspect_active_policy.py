
from pathlib import Path
import sys
import json

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.services.procurement.policy_service import PolicyService


print("\n==========================================")
print("ACTIVE PROCUREMENT POLICY INSPECTION")
print("==========================================")

db = SessionLocal()

try:
    active_policy = PolicyService(db).get_active_policy()

    print("\nPolicy version:", active_policy["version"])
    print("Effective date:", active_policy["effective_date"])

    policy_data = active_policy["policy_data"]

    print("\nCOMPLETE POLICY DATA:")
    print(json.dumps(
        policy_data,
        indent=4,
        default=str
    ))

    print("\n==========================================")
    print("AVAILABLE POLICY KEYS")
    print("==========================================")

    def display_keys(data, parent="policy"):

        if not isinstance(data, dict):
            return

        for key, value in data.items():

            current_path = f"{parent}.{key}"

            if isinstance(value, dict):
                print(f"\n{current_path}:")
                display_keys(value, current_path)
            else:
                print(f"{current_path} = {value}")

    display_keys(policy_data)

finally:
    db.close()

print("\nPOLICY INSPECTION COMPLETED.")
