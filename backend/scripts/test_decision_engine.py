
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal

from app.services.procurement.policy_service import (
    PolicyService
)

from app.services.procurement.decision_engine import (
    ProcurementDecisionEngine
)


# =============================================
# 1. LOAD ACTIVE POLICY
# =============================================

db = SessionLocal()

try:
    active_policy = PolicyService(db).get_active_policy()
finally:
    db.close()

policy_data = active_policy["policy_data"]

engine = ProcurementDecisionEngine(policy_data)

print("\n==========================================")
print("PROCUREMENT DECISION ENGINE TEST")
print("==========================================")

print("Policy version:", active_policy["version"])
print("Effective date:", active_policy["effective_date"])


# =============================================
# 2. READ THRESHOLDS FROM POLICY
# =============================================

def get_rule(route):

    for rule in policy_data["rules"]:
        if rule["then"].get("route") == route:
            return rule

    raise ValueError(f"Policy route not found: {route}")


emergency_rule = get_rule("EMERGENCY_PO")
spot_rule = get_rule("SPOT_PO")
rfq_rule = get_rule("RFQ")
rfp_rule = get_rule("RFP")

emergency_limit = float(
    emergency_rule["when"]["max_value_inr"]
)

spot_limit = float(
    spot_rule["when"]["max_value_exclusive_inr"]
)

rfq_limit = float(
    rfq_rule["when"]["max_value_exclusive_inr"]
)

rfp_limit = float(
    rfp_rule["when"]["min_value_inclusive_inr"]
)

emergency_lookback = int(
    emergency_rule["when"][
        "purchased_from_active_supplier_within_days"
    ]
)

spot_lookback = int(
    spot_rule["when"][
        "purchased_from_active_supplier_within_days"
    ]
)


# =============================================
# 3. DEFINE TEST CASES
# =============================================

test_cases = [
    {
        "name": "New item sourcing",
        "request": {
            "item_code": None,
            "is_new_item": True,
            "total_value": 100000,
        },
        "expected": "NEW_ITEM_SOURCING",
    },
    {
        "name": "Capex sourcing",
        "request": {
            "item_code": "ITM-1001",
            "item_type": "Capex",
            "total_value": 500000,
        },
        "expected": "CAPEX_SOURCING",
    },
    {
        "name": "Contract PO",
        "request": {
            "item_code": "ITM-1001",
            "has_usable_contract": True,
            "total_value": 300000,
        },
        "expected": "CONTRACT_PO",
    },
    {
        "name": "Emergency PO",
        "request": {
            "item_code": "ITM-1001",
            "urgency": "Emergency",
            "total_value": emergency_limit,
            "has_active_supplier": True,
            "days_since_last_purchase": emergency_lookback,
        },
        "expected": "EMERGENCY_PO",
    },
    {
        "name": "Spot PO",
        "request": {
            "item_code": "ITM-1001",
            "urgency": "Normal",
            "total_value": spot_limit - 1,
            "has_active_supplier": True,
            "days_since_last_purchase": spot_lookback,
        },
        "expected": "SPOT_PO",
    },
    {
        "name": "RFQ",
        "request": {
            "item_code": "ITM-1001",
            "urgency": "Normal",
            "total_value": spot_limit,
            "has_active_supplier": False,
        },
        "expected": "RFQ",
    },
    {
        "name": "RFP",
        "request": {
            "item_code": "ITM-1001",
            "urgency": "Normal",
            "total_value": rfp_limit,
            "has_active_supplier": False,
        },
        "expected": "RFP",
    },
    {
        "name": "Emergency without recent purchase",
        "request": {
            "item_code": "ITM-1001",
            "urgency": "Emergency",
            "total_value": emergency_limit,
            "has_active_supplier": True,
            "days_since_last_purchase": emergency_lookback + 1,
        },
        "expected": (
            "RFQ"
            if emergency_limit < rfq_limit
            else "RFP"
        ),
    },
]


# =============================================
# 4. RUN TEST CASES
# =============================================

passed = 0
failed = 0

for test in test_cases:

    print("\n------------------------------------------")
    print("Test:", test["name"])

    result = engine.decide(
        test["request"]
    )

    actual = result["decision"]
    expected = test["expected"]

    print("Expected:", expected)
    print("Actual:", actual)
    print("Policy rule:", result["policy_rule_id"])
    print("Action:", result["action"])
    print("Reason:", result["reason"])

    if "suggested_supplier_count" in result:
        print(
            "Suggested suppliers:",
            result["suggested_supplier_count"]
        )

    if actual == expected:
        print("Status: PASS")
        passed += 1
    else:
        print("Status: FAIL")
        failed += 1


# =============================================
# 5. TEST BOUNDARIES
# =============================================

print("\n==========================================")
print("POLICY BOUNDARY TESTS")
print("==========================================")

boundary_cases = [
    {
        "name": "RFQ below RFP threshold",
        "value": rfp_limit - 0.01,
        "expected": "RFQ",
    },
    {
        "name": "RFP at inclusive threshold",
        "value": rfp_limit,
        "expected": "RFP",
    },
    {
        "name": "Spot threshold is exclusive",
        "value": spot_limit,
        "expected": "RFQ",
    },
]

for test in boundary_cases:

    result = engine.decide({
        "item_code": "ITM-1001",
        "total_value": test["value"],
        "urgency": "Normal",
        "has_active_supplier": False,
    })

    success = result["decision"] == test["expected"]

    print(
        test["name"],
        "->",
        result["decision"],
        "->",
        "PASS" if success else "FAIL",
    )

    if success:
        passed += 1
    else:
        failed += 1


# =============================================
# 6. FINAL RESULT
# =============================================

print("\n==========================================")
print("FINAL TEST RESULTS")
print("==========================================")

print("Passed:", passed)
print("Failed:", failed)
print("Total:", passed + failed)

if failed > 0:
    raise AssertionError(
        f"{failed} procurement decision tests failed."
    )

print("\nALL PROCUREMENT DECISION TESTS PASSED.")
