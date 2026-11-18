
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.services.procurement.validation import ProcurementValidator
from app.services.procurement.clubbing_service import RequirementClubbingService
from app.services.procurement.valuation import ProcurementValuator
from app.services.procurement.contract_service import ContractAllocationService
from app.services.procurement.decision_engine import ProcurementDecisionEngine
from app.services.procurement.supplier_service import SupplierService
from app.services.procurement.recommendation_service import (
    SupplierRecommendationService,
)


class ProcurementOrchestrationService:
    """
    Coordinates the procurement services into one workflow.

    Workflow:
        1. Validate purchase request lines.
        2. Club eligible requirements.
        3. Summarize consolidated requirements.
        4. Allocate applicable contracts.
        5. Calculate requirement valuation.
        6. Apply procurement decision rules.
        7. Recommend suppliers where required.
        8. Return requirement-level and original-line results.

    This service does not persist contract balances or decisions to
    PostgreSQL. Contract allocations are maintained in memory by the
    ContractAllocationService instance.
    """

    def __init__(
        self,
        policy_data: dict,
        item_master: pd.DataFrame,
        plants: pd.DataFrame,
        supplier_master: pd.DataFrame,
        po_history: pd.DataFrame,
        contract_register: pd.DataFrame,
        contract_lines: pd.DataFrame,
        ranking_weights: dict,
    ):
        self.policy_data = policy_data

        # Keep copies so the orchestration service does not modify
        # the caller's original dataframes.
        self.item_master = item_master.copy()
        self.plants = plants.copy()
        self.supplier_master = supplier_master.copy()
        self.po_history = po_history.copy()
        self.contract_register = contract_register.copy()
        self.contract_lines = contract_lines.copy()

        # Normalize master-data identifiers.
        self.item_master["item_code"] = (
            self.item_master["item_code"].astype("string").str.strip()
        )

        self.plants["plant"] = (
            self.plants["plant"].astype("string").str.strip()
        )

        self.supplier_master["supplier_id"] = (
            self.supplier_master["supplier_id"]
            .astype("string")
            .str.strip()
        )

        # Initialize procurement services.
        self.validator = ProcurementValidator(
            item_master=self.item_master,
            plants=self.plants,
        )

        self.clubbing_service = RequirementClubbingService(
            policy_data=self.policy_data
        )

        self.valuator = ProcurementValuator(
            contract_lines=self.contract_lines,
            contract_register=self.contract_register,
            po_history=self.po_history,
            item_master=self.item_master,
            supplier_master=self.supplier_master,
        )

        self.contract_service = ContractAllocationService(
            contract_lines=self.contract_lines,
            contract_register=self.contract_register,
            supplier_master=self.supplier_master,
            policy_data=self.policy_data,
        )

        self.decision_engine = ProcurementDecisionEngine(
            policy_data=self.policy_data
        )

        self.supplier_service = SupplierService(
            supplier_master=self.supplier_master,
            po_history=self.po_history,
            contract_register=self.contract_register,
            item_master=self.item_master,
            ranking_weights=ranking_weights,
        )

        self.recommendation_service = SupplierRecommendationService(
            supplier_service=self.supplier_service,
            supplier_master=self.supplier_master,
            po_history=self.po_history,
            contract_lines=self.contract_lines,
            contract_register=self.contract_register,
            item_master=self.item_master,
        )

    # =========================================================
    # 1. INPUT VALIDATION
    # =========================================================

    def _validate_request_lines(
        self,
        requests: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Validate individual PR lines before clubbing.

        Missing item codes are permitted because they represent
        new-item sourcing requests under policy rule 1.2.

        Unknown non-empty item codes and invalid plants are rejected.
        """

        if not isinstance(requests, pd.DataFrame):
            raise TypeError("requests must be a pandas DataFrame.")

        if requests.empty:
            raise ValueError("No purchase request lines were supplied.")

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

        missing_columns = required_columns - set(requests.columns)

        if missing_columns:
            raise ValueError(
                "Purchase request data is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        df = requests.copy().reset_index(drop=True)

        df["created_at"] = pd.to_datetime(
            df["created_at"],
            errors="coerce",
        )

        df["need_by_date"] = pd.to_datetime(
            df["need_by_date"],
            errors="coerce",
        )

        df["quantity"] = pd.to_numeric(
            df["quantity"],
            errors="coerce",
        )

        if "item_code" in df.columns:
            df["item_code"] = df["item_code"].replace(
                r"^\s*$",
                pd.NA,
                regex=True,
            )

        valid_item_codes = set(
            self.item_master["item_code"].dropna().astype(str)
        )

        valid_plants = set(
            self.plants["plant"].dropna().astype(str)
        )

        valid_rows = []
        invalid_rows = []

        for _, row in df.iterrows():
            errors = []

            if pd.isna(row["pr_no"]) or pd.isna(row["pr_line"]):
                errors.append("MISSING_PR_REFERENCE")

            if pd.isna(row["created_at"]):
                errors.append("INVALID_CREATED_DATE")

            if pd.isna(row["need_by_date"]):
                errors.append("INVALID_NEED_BY_DATE")

            if pd.isna(row["quantity"]) or row["quantity"] <= 0:
                errors.append("INVALID_QUANTITY")

            plant = row["plant"]

            if (
                pd.isna(plant)
                or str(plant).strip() not in valid_plants
            ):
                errors.append("INVALID_PLANT")

            item_code = row["item_code"]

            # Missing item code means new item.
            if pd.notna(item_code):
                if str(item_code).strip() not in valid_item_codes:
                    errors.append("UNKNOWN_ITEM_CODE")

            result = row.to_dict()

            if errors:
                result["line_status"] = "INVALID"
                result["validation_errors"] = errors
                invalid_rows.append(result)
            else:
                result["line_status"] = "VALID"
                result["validation_errors"] = []
                valid_rows.append(result)

        valid_df = pd.DataFrame(valid_rows)
        invalid_df = pd.DataFrame(invalid_rows)

        return valid_df, invalid_df

    # =========================================================
    # 2. ITEM MASTER DETAILS
    # =========================================================

    def _get_item_details(self, item_code: Any) -> dict:
        if item_code is None or pd.isna(item_code):
            return {
                "category": None,
                "item_type": None,
                "is_new_item": True,
            }

        matches = self.item_master[
            self.item_master["item_code"].astype(str)
            == str(item_code)
        ]

        if matches.empty:
            return {
                "category": None,
                "item_type": None,
                "is_new_item": True,
            }

        item = matches.iloc[0]

        return {
            "category": item.get("category"),
            "item_type": item.get("item_type"),
            "is_new_item": False,
        }

    # =========================================================
    # 3. RECENT ACTIVE SUPPLIER PURCHASE EVIDENCE
    # =========================================================

    def _get_recent_purchase_evidence(
        self,
        item_code: Any,
        calculation_date: Any,
        lookback_days: int = 365,
    ) -> dict:
        """
        Check whether the item was purchased from an active supplier
        within the policy's specified lookback period.
        """

        if item_code is None or pd.isna(item_code):
            return {
                "has_active_supplier": False,
                "days_since_last_purchase": None,
            }

        calculation_date = pd.Timestamp(calculation_date)

        active_suppliers = set(
            self.supplier_master.loc[
                self.supplier_master["status"]
                .astype(str)
                .str.strip()
                .str.casefold()
                .eq("active"),
                "supplier_id",
            ].dropna().astype(str)
        )

        history = self.po_history.copy()

        history["po_date"] = pd.to_datetime(
            history["po_date"],
            errors="coerce",
        )

        history["supplier_id"] = (
            history["supplier_id"].astype(str).str.strip()
        )

        history = history[
            (history["item_code"].astype(str) == str(item_code))
            & history["supplier_id"].isin(active_suppliers)
            & history["po_date"].notna()
            & (history["po_date"] <= calculation_date)
            & (
                history["po_date"]
                >= calculation_date - pd.Timedelta(days=lookback_days)
            )
        ]

        if history.empty:
            return {
                "has_active_supplier": False,
                "days_since_last_purchase": None,
            }

        latest_purchase = history["po_date"].max()

        days_since = (
            calculation_date.normalize()
            - latest_purchase.normalize()
        ).days

        return {
            "has_active_supplier": True,
            "days_since_last_purchase": days_since,
        }

    # =========================================================
    # 4. REQUIREMENT VALUATION
    # =========================================================

    def _value_requirement(
        self,
        requirement: dict,
        allocation: dict,
    ) -> dict:
        """
        Use the allocated contract rate when a contract was actually
        allocated. Otherwise, use the valuation service's fallback
        hierarchy.
        """

        requirement_id = requirement["requirement_id"]

        if allocation.get("allocation_status") == "ALLOCATED":
            rate = float(allocation["contract_rate"])
            total_value = float(allocation["allocated_value"])

            return {
                "requirement_id": requirement_id,
                "status": "VALUED",
                "unit_price": rate,
                "total_value": total_value,
                "source": "ALLOCATED_CONTRACT_RATE",
                "contract_id": allocation.get("contract_id"),
                "supplier_id": allocation.get("supplier_id"),
            }

        item_code = requirement.get("item_code")
        quantity = requirement.get("total_quantity")
        calculation_date = requirement.get("created_at")

        estimate = requirement.get("estimated_unit_price")

        result = self.valuator.value_request(
            item_code=item_code,
            quantity=quantity,
            calculation_date=calculation_date,
            estimated_unit_price=estimate,
        )

        return {
            "requirement_id": requirement_id,
            **result,
        }

    # =========================================================
    # 5. PROCUREMENT DECISION
    # =========================================================

    def _decide_requirement(
        self,
        requirement: dict,
        valuation: dict,
        allocation: dict,
        item_details: dict,
    ) -> dict:
        requirement_id = requirement["requirement_id"]

        if valuation.get("total_value") is None:
            return {
                "requirement_id": requirement_id,
                "decision_status": "VALUATION_REQUIRED",
                "decision": None,
                "route": None,
                "action": None,
                "reason": (
                    "A valid estimated or reference price is required "
                    "before a procurement route can be selected."
                ),
                "policy_rule_id": None,
            }

        allocation_status = allocation.get("allocation_status")

        request = {
            "item_code": requirement.get("item_code"),
            "is_new_item": item_details["is_new_item"],
            "item_type": item_details["item_type"],
            "total_value": valuation["total_value"],
            "urgency": (
                "Emergency"
                if requirement.get("is_emergency")
                else "Normal"
            ),
            "allocation_status": allocation_status,
            "has_usable_contract": allocation_status == "ALLOCATED",
        }

        purchase_evidence = self._get_recent_purchase_evidence(
            item_code=requirement.get("item_code"),
            calculation_date=requirement["created_at"],
            lookback_days=365,
        )

        request.update(purchase_evidence)

        result = self.decision_engine.decide(request)

        return {
            "requirement_id": requirement_id,
            "decision_status": "DECIDED",
            **result,
        }

    # =========================================================
    # 6. SUPPLIER RECOMMENDATIONS
    # =========================================================

    def _recommend_suppliers(
        self,
        requirement: dict,
        decision: dict,
        item_details: dict,
    ) -> dict:
        requirement_id = requirement["requirement_id"]

        supplier_count = decision.get("supplier_count", 0)

        if (
            decision.get("action") != "SOURCING_REQUEST"
            or supplier_count not in (3, 5)
        ):
            return {
                "requirement_id": requirement_id,
                "status": "NOT_REQUIRED",
                "supplier_count_requested": 0,
                "supplier_count_returned": 0,
                "suppliers": [],
            }

        result = self.recommendation_service.recommend_suppliers(
            item_code=requirement.get("item_code"),
            category=item_details["category"],
            calculation_date=requirement["created_at"],
            supplier_count=supplier_count,
            is_new_item=item_details["is_new_item"],
        )

        return {
            "requirement_id": requirement_id,
            **result,
        }

    # =========================================================
    # 7. MAIN PROCUREMENT WORKFLOW
    # =========================================================

    def process_requests(
        self,
        requests: pd.DataFrame,
    ) -> dict:
        """
        Execute the procurement workflow for a batch of PR lines.

        Returns:
            valid_lines
            invalid_lines
            clubbed_lines
            requirement_summary
            contract_allocations
            requirement_results
            final_line_results
            contract_balances
        """

        valid_lines, invalid_lines = self._validate_request_lines(
            requests
        )

        if valid_lines.empty:
            return {
                "valid_lines": valid_lines,
                "invalid_lines": invalid_lines,
                "clubbed_lines": pd.DataFrame(),
                "requirement_summary": pd.DataFrame(),
                "contract_allocations": pd.DataFrame(),
                "requirement_results": pd.DataFrame(),
                "final_line_results": invalid_lines.copy(),
                "contract_balances": (
                    self.contract_service.get_contract_balance_summary()
                ),
            }

        # -----------------------------------------------------
        # STEP 1: CLUB REQUIREMENTS
        # -----------------------------------------------------

        clubbed_lines = self.clubbing_service.club_requirements(
            valid_lines
        )

        requirement_summary = (
            self.clubbing_service.get_requirement_summary(
                clubbed_lines
            )
        )

        # Preserve requester estimates for new-item valuation.
        if "estimated_unit_price" in clubbed_lines.columns:
            estimates = (
                clubbed_lines
                .groupby("requirement_id")["estimated_unit_price"]
                .first()
                .rename("estimated_unit_price")
            )

            requirement_summary = requirement_summary.merge(
                estimates,
                on="requirement_id",
                how="left",
            )

        else:
            requirement_summary["estimated_unit_price"] = None

        # -----------------------------------------------------
        # STEP 2: CONTRACT ALLOCATION
        # -----------------------------------------------------

        contract_allocations = (
            self.contract_service.allocate_requirements(
                requirement_summary[
                    [
                        "requirement_id",
                        "item_code",
                        "total_quantity",
                        "created_at",
                    ]
                ]
            )
        )

        # -----------------------------------------------------
        # STEP 3: PROCESS EACH CONSOLIDATED REQUIREMENT
        # -----------------------------------------------------

        allocation_lookup = {
            row["requirement_id"]: row
            for row in contract_allocations.to_dict("records")
        }

        requirement_results = []

        for requirement in requirement_summary.to_dict("records"):
            requirement_id = requirement["requirement_id"]

            allocation = allocation_lookup.get(
                requirement_id,
                {
                    "requirement_id": requirement_id,
                    "allocation_status": "NO_APPLICABLE_CONTRACT",
                    "contract_id": None,
                    "supplier_id": None,
                    "contract_rate": None,
                    "allocated_value": None,
                    "reason": "No contract allocation result found.",
                },
            )

            item_details = self._get_item_details(
                requirement.get("item_code")
            )

            valuation = self._value_requirement(
                requirement=requirement,
                allocation=allocation,
            )

            decision = self._decide_requirement(
                requirement=requirement,
                valuation=valuation,
                allocation=allocation,
                item_details=item_details,
            )

            recommendations = self._recommend_suppliers(
                requirement=requirement,
                decision=decision,
                item_details=item_details,
            )

            requirement_results.append({
                "requirement_id": requirement_id,
                "item_code": requirement.get("item_code"),
                "plant": requirement.get("plant"),
                "created_at": requirement.get("created_at"),
                "need_by_date": requirement.get("need_by_date"),
                "total_quantity": requirement.get("total_quantity"),
                "line_count": requirement.get("line_count"),
                "is_new_item": item_details["is_new_item"],
                "is_emergency": requirement.get("is_emergency"),
                "category": item_details["category"],
                "item_type": item_details["item_type"],
                "valuation_status": valuation.get("status"),
                "unit_price": valuation.get("unit_price"),
                "total_value": valuation.get("total_value"),
                "valuation_source": valuation.get("source"),
                "contract_allocation_status": allocation.get(
                    "allocation_status"
                ),
                "contract_id": allocation.get("contract_id"),
                "contract_supplier_id": allocation.get("supplier_id"),
                "decision_status": decision.get("decision_status"),
                "decision": decision.get("decision"),
                "route": decision.get("route"),
                "action": decision.get("action"),
                "policy_rule_id": decision.get("policy_rule_id"),
                "decision_reason": decision.get("reason"),
                "supplier_recommendation_status": recommendations.get(
                    "status"
                ),
                "supplier_count_requested": recommendations.get(
                    "supplier_count_requested", 0
                ),
                "supplier_count_returned": recommendations.get(
                    "supplier_count_returned", 0
                ),
                "recommended_suppliers": recommendations.get(
                    "suppliers", []
                ),
                "valuation_details": valuation,
                "allocation_details": allocation,
                "decision_details": decision,
            })

        requirement_results_df = pd.DataFrame(requirement_results)

        # -----------------------------------------------------
        # STEP 4: MAP RESULTS BACK TO ORIGINAL PR LINES
        # -----------------------------------------------------

        final_line_results = clubbed_lines.merge(
            requirement_results_df,
            on="requirement_id",
            how="left",
            suffixes=("", "_requirement"),
        )

        final_line_results["line_status"] = "PROCESSED"

        # Include invalid source lines in the final output.
        if not invalid_lines.empty:
            invalid_output = invalid_lines.copy()

            for column in final_line_results.columns:
                if column not in invalid_output.columns:
                    invalid_output[column] = None

            invalid_output = invalid_output[
                final_line_results.columns
            ]

            final_line_results = pd.concat(
                [final_line_results, invalid_output],
                ignore_index=True,
            )

        # -----------------------------------------------------
        # STEP 5: CONTRACT BALANCE SUMMARY
        # -----------------------------------------------------

        contract_balances = (
            self.contract_service.get_contract_balance_summary()
        )

        return {
            "valid_lines": valid_lines,
            "invalid_lines": invalid_lines,
            "clubbed_lines": clubbed_lines,
            "requirement_summary": requirement_summary,
            "contract_allocations": contract_allocations,
            "requirement_results": requirement_results_df,
            "final_line_results": final_line_results,
            "contract_balances": contract_balances,
        }
