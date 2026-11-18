
class ProcurementDecisionEngine:
    """
    Data-driven procurement decision engine.
    Reads procurement routes and thresholds from the active policy.
    """

    def __init__(self, policy_data: dict):
        if not isinstance(policy_data, dict):
            raise ValueError("policy_data must be a dictionary.")

        self.policy = policy_data
        self.rules = self._load_rules()

    def _load_rules(self):
        rules = self.policy.get("rules")

        if not isinstance(rules, list) or not rules:
            raise ValueError("Policy must contain a non-empty rules list.")

        required_routes = {
            "NEW_ITEM_SOURCING",
            "CAPEX_SOURCING",
            "CONTRACT_PO",
            "EMERGENCY_PO",
            "SPOT_PO",
            "RFQ",
            "RFP",
        }

        route_map = {}

        for rule in rules:
            route = rule.get("then", {}).get("route")

            if route:
                if route in route_map:
                    raise ValueError(f"Duplicate policy route: {route}")
                route_map[route] = rule

        missing = required_routes - set(route_map)

        if missing:
            raise ValueError(
                f"Policy is missing required routes: {sorted(missing)}"
            )

        return sorted(
            rules,
            key=lambda rule: rule.get("priority", 9999)
        )

    def _get_rule(self, route: str) -> dict:
        for rule in self.rules:
            if rule.get("then", {}).get("route") == route:
                return rule

        raise ValueError(f"Policy rule not found: {route}")

    @staticmethod
    def _has_recent_active_supplier_purchase(
        request: dict,
        lookback_days: int
    ) -> bool:
        if not request.get("has_active_supplier", False):
            return False

        days_since_purchase = request.get("days_since_last_purchase")

        if days_since_purchase is not None:
            try:
                return 0 <= float(days_since_purchase) <= lookback_days
            except (TypeError, ValueError):
                return False

        return request.get("recent_purchase") is True

    @staticmethod
    def _has_usable_contract(request: dict) -> bool:
        """
        Recognizes contract availability from the decision request
        and successful contract allocation results.
        """

        if (
            request.get("usable_contract") is True
            or request.get("has_usable_contract") is True
        ):
            return True

        contract_status = str(
            request.get("contract_status", "")
        ).strip().upper()

        allocation_status = str(
            request.get("allocation_status", "")
        ).strip().upper()

        if contract_status == "ALLOCATED":
            return True

        if allocation_status == "ALLOCATED":
            return True

        if (
            request.get("contract_id")
            and request.get("contract_supplier")
        ):
            return True

        if request.get("allocated_contract_id"):
            return True

        return False

    def _build_result(self, rule: dict, reason: str) -> dict:
        then = rule["then"]

        return {
            "decision": then["route"],
            "route": then["route"],
            "action": then.get("decision"),
            "policy_rule_id": rule.get("id"),
            "policy_priority": rule.get("priority"),
            "reason": reason,
            "supplier_count": then.get("supplier_count", 0),
            "requires_capex_approval": then.get(
                "requires_capex_approval", False
            ),
            "never_club": then.get("never_club", False),
        }

    def decide(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise ValueError("request must be a dictionary.")

        if request.get("total_value") is None:
            raise ValueError("Request must contain total_value.")

        try:
            total_value = float(request["total_value"])
        except (TypeError, ValueError):
            raise ValueError("total_value must be numeric.")

        if total_value < 0:
            raise ValueError("total_value cannot be negative.")

        # Rule 1.2: New item sourcing
        if (
            request.get("is_new_item", False)
            or request.get("item_match") == "NEW"
            or request.get("item_code") is None
        ):
            rule = self._get_rule("NEW_ITEM_SOURCING")
            return self._build_result(
                rule,
                "New item requires a sourcing request."
            )

        # Rule 5.1: Capex sourcing
        if str(request.get("item_type", "")).strip().lower() == "capex":
            rule = self._get_rule("CAPEX_SOURCING")
            return self._build_result(
                rule,
                "Capital expenditure requires sourcing and approval."
            )

        # Rule 5.2: Usable contract
        if self._has_usable_contract(request):
            rule = self._get_rule("CONTRACT_PO")
            return self._build_result(
                rule,
                "A usable contract is available for this requirement."
            )

        # Rule 5.3: Emergency PO
        emergency_rule = self._get_rule("EMERGENCY_PO")
        emergency_conditions = emergency_rule["when"]

        emergency_limit = float(
            emergency_conditions["max_value_inr"]
        )
        emergency_days = int(
            emergency_conditions[
                "purchased_from_active_supplier_within_days"
            ]
        )

        is_emergency = (
            str(request.get("urgency", "")).strip().lower()
            == "emergency"
        )

        if (
            is_emergency
            and total_value <= emergency_limit
            and self._has_recent_active_supplier_purchase(
                request,
                emergency_days
            )
        ):
            return self._build_result(
                emergency_rule,
                "Emergency requirement qualifies for an emergency PO."
            )

        # Rule 5.4: Spot PO
        spot_rule = self._get_rule("SPOT_PO")
        spot_conditions = spot_rule["when"]

        spot_limit = float(
            spot_conditions["max_value_exclusive_inr"]
        )
        spot_days = int(
            spot_conditions[
                "purchased_from_active_supplier_within_days"
            ]
        )

        if (
            total_value < spot_limit
            and self._has_recent_active_supplier_purchase(
                request,
                spot_days
            )
        ):
            return self._build_result(
                spot_rule,
                "Small purchase qualifies for a spot PO."
            )

        # Rule 5.5: RFQ
        rfq_rule = self._get_rule("RFQ")
        rfq_limit = float(
            rfq_rule["when"]["max_value_exclusive_inr"]
        )

        if total_value < rfq_limit:
            return self._build_result(
                rfq_rule,
                "Requirement falls within the RFQ value range."
            )

        # Rule 5.6: RFP
        rfp_rule = self._get_rule("RFP")
        rfp_limit = float(
            rfp_rule["when"]["min_value_inclusive_inr"]
        )

        if total_value >= rfp_limit:
            return self._build_result(
                rfp_rule,
                "Requirement falls within the RFP value range."
            )

        raise ValueError(
            "No procurement rule matched this request. "
            "Check the policy thresholds."
        )
