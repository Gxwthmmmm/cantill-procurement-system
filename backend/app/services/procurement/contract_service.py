
import pandas as pd


class ContractAllocationService:
    """
    Allocates purchase requirements against applicable contracts.

    Procurement rules:
    - Contract validity dates are inclusive.
    - Only active suppliers are eligible.
    - Contract ceiling must cover the complete requirement.
    - Lowest-rate usable contract is selected.
    - Requirements are processed in creation-date order.
    - New items cannot use existing contracts.
    """

    REQUIRED_REQUIREMENT_COLUMNS = {
        "requirement_id",
        "item_code",
        "total_quantity",
        "created_at",
    }

    def __init__(
        self,
        contract_lines,
        contract_register,
        supplier_master,
        policy_data,
    ):
        self.contract_lines = contract_lines.copy()
        self.contracts = contract_register.copy()
        self.suppliers = supplier_master.copy()

        self.policy = policy_data.get("contracts", {})

        # -----------------------------------------
        # CONVERT DATA TYPES
        # -----------------------------------------

        self.contracts["start_date"] = pd.to_datetime(
            self.contracts["start_date"],
            errors="coerce",
        )

        self.contracts["end_date"] = pd.to_datetime(
            self.contracts["end_date"],
            errors="coerce",
        )

        self.contracts["value_cap"] = pd.to_numeric(
            self.contracts["value_cap"],
            errors="coerce",
        ).astype(float)

        self.contracts["consumed_value"] = pd.to_numeric(
            self.contracts["consumed_value"],
            errors="coerce",
        ).astype(float)

        self.contract_lines["rate"] = pd.to_numeric(
            self.contract_lines["rate"],
            errors="coerce",
        ).astype(float)

        # -----------------------------------------
        # IDENTIFY ACTIVE SUPPLIERS
        # -----------------------------------------

        active_mask = (
            self.suppliers["status"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq("active")
        )

        self.active_supplier_ids = set(
            self.suppliers.loc[
                active_mask,
                "supplier_id",
            ]
        )

        # -----------------------------------------
        # INITIALIZE WORKING CONTRACT BALANCES
        # -----------------------------------------

        self.contract_balances = self.contracts[
            [
                "contract_id",
                "supplier_id",
                "value_cap",
                "consumed_value",
            ]
        ].copy()

        self.contract_balances["value_cap"] = (
            self.contract_balances["value_cap"].astype(float)
        )

        self.contract_balances["consumed_value"] = (
            self.contract_balances["consumed_value"].astype(float)
        )

        self.contract_balances["remaining_value"] = (
            self.contract_balances["value_cap"]
            - self.contract_balances["consumed_value"]
        ).astype(float)

    # =============================================
    # 1. VALIDATE REQUIREMENT INPUT
    # =============================================

    def _validate_requirements(self, requirements):

        missing = (
            self.REQUIRED_REQUIREMENT_COLUMNS
            - set(requirements.columns)
        )

        if missing:
            raise ValueError(
                f"Missing requirement columns: {sorted(missing)}"
            )

    # =============================================
    # 2. FIND APPLICABLE CONTRACTS
    # =============================================

    def get_applicable_contracts(
        self,
        item_code,
        calculation_date,
    ):

        calculation_date = pd.Timestamp(calculation_date)

        item_lines = self.contract_lines[
            self.contract_lines["item_code"] == item_code
        ].copy()

        if item_lines.empty:
            return pd.DataFrame()

        applicable = item_lines.merge(
            self.contracts,
            on="contract_id",
            how="inner",
        )

        # Contract validity dates are inclusive.
        applicable = applicable[
            applicable["start_date"].notna()
            & applicable["end_date"].notna()
            & (applicable["start_date"] <= calculation_date)
            & (applicable["end_date"] >= calculation_date)
        ].copy()

        if applicable.empty:
            return applicable

        # Only active suppliers can receive contract POs.
        applicable = applicable[
            applicable["supplier_id"].isin(
                self.active_supplier_ids
            )
        ].copy()

        if applicable.empty:
            return applicable

        # Attach current working contract balances.
        applicable = applicable.merge(
            self.contract_balances[
                ["contract_id", "remaining_value"]
            ],
            on="contract_id",
            how="left",
        )

        applicable = applicable[
            applicable["rate"].notna()
            & (applicable["rate"] > 0)
            & applicable["remaining_value"].notna()
        ].copy()

        return applicable

    # =============================================
    # 3. ALLOCATE ONE REQUIREMENT
    # =============================================

    def allocate_one_requirement(self, requirement):

        requirement_id = requirement["requirement_id"]
        item_code = requirement["item_code"]

        quantity = float(requirement["total_quantity"])

        calculation_date = pd.Timestamp(
            requirement["created_at"]
        )

        # -----------------------------------------
        # VALIDATE ITEM CODE
        # -----------------------------------------

        if pd.isna(item_code) or str(item_code).strip() == "":
            return {
                "requirement_id": requirement_id,
                "allocation_status": "NEW_ITEM_NO_CONTRACT",
                "contract_id": None,
                "supplier_id": None,
                "contract_rate": None,
                "allocated_value": None,
                "remaining_value": None,
                "reason": (
                    "New items cannot use existing contracts."
                ),
            }

        # -----------------------------------------
        # VALIDATE QUANTITY
        # -----------------------------------------

        if pd.isna(quantity) or quantity <= 0:
            return {
                "requirement_id": requirement_id,
                "allocation_status": "INVALID_QUANTITY",
                "contract_id": None,
                "supplier_id": None,
                "contract_rate": None,
                "allocated_value": None,
                "remaining_value": None,
                "reason": (
                    "Requirement quantity must be positive."
                ),
            }

        # -----------------------------------------
        # FIND APPLICABLE CONTRACTS
        # -----------------------------------------

        applicable = self.get_applicable_contracts(
            item_code=item_code,
            calculation_date=calculation_date,
        )

        if applicable.empty:
            return {
                "requirement_id": requirement_id,
                "allocation_status": "NO_APPLICABLE_CONTRACT",
                "contract_id": None,
                "supplier_id": None,
                "contract_rate": None,
                "allocated_value": None,
                "remaining_value": None,
                "reason": (
                    "No valid contract with an active supplier "
                    "was found for this item."
                ),
            }

        # -----------------------------------------
        # CALCULATE REQUIREMENT VALUE
        # -----------------------------------------

        applicable["requirement_value"] = (
            applicable["rate"] * quantity
        )

        # -----------------------------------------
        # CHECK CONTRACT CEILING
        # -----------------------------------------

        usable = applicable[
            applicable["remaining_value"]
            >= applicable["requirement_value"]
        ].copy()

        if usable.empty:

            lowest_rate = applicable.sort_values(
                by=["rate", "contract_id"],
                ascending=[True, True],
            ).iloc[0]

            return {
                "requirement_id": requirement_id,
                "allocation_status": "CONTRACT_CEILING_EXCEEDED",
                "contract_id": None,
                "supplier_id": None,
                "contract_rate": float(lowest_rate["rate"]),
                "allocated_value": None,
                "remaining_value": float(
                    lowest_rate["remaining_value"]
                ),
                "reason": (
                    "Applicable contracts exist, but none has "
                    "sufficient remaining ceiling."
                ),
            }

        # -----------------------------------------
        # SELECT LOWEST-RATE USABLE CONTRACT
        # -----------------------------------------

        selected = usable.sort_values(
            by=["rate", "contract_id"],
            ascending=[True, True],
        ).iloc[0]

        contract_id = selected["contract_id"]

        allocated_value = float(
            selected["rate"] * quantity
        )

        # -----------------------------------------
        # UPDATE WORKING CONTRACT BALANCE
        # -----------------------------------------

        matching_indices = self.contract_balances.index[
            self.contract_balances["contract_id"] == contract_id
        ]

        if len(matching_indices) != 1:
            raise ValueError(
                f"Expected one balance row for contract {contract_id}."
            )

        balance_index = matching_indices[0]

        self.contract_balances.loc[
            balance_index,
            "consumed_value",
        ] = (
            float(
                self.contract_balances.loc[
                    balance_index,
                    "consumed_value",
                ]
            )
            + allocated_value
        )

        self.contract_balances.loc[
            balance_index,
            "remaining_value",
        ] = (
            float(
                self.contract_balances.loc[
                    balance_index,
                    "remaining_value",
                ]
            )
            - allocated_value
        )

        remaining_value = float(
            self.contract_balances.loc[
                balance_index,
                "remaining_value",
            ]
        )

        return {
            "requirement_id": requirement_id,
            "allocation_status": "ALLOCATED",
            "contract_id": contract_id,
            "supplier_id": selected["supplier_id"],
            "contract_rate": float(selected["rate"]),
            "allocated_value": allocated_value,
            "remaining_value": remaining_value,
            "reason": (
                "Lowest-rate contract with sufficient ceiling selected."
            ),
        }

    # =============================================
    # 4. ALLOCATE ALL REQUIREMENTS
    # =============================================

    def allocate_requirements(self, requirements):

        self._validate_requirements(requirements)

        df = requirements.copy()

        df["created_at"] = pd.to_datetime(
            df["created_at"],
            errors="coerce",
        )

        if df["created_at"].isna().any():
            raise ValueError(
                "Requirements contain invalid creation dates."
            )

        if df["requirement_id"].duplicated().any():
            raise ValueError(
                "Duplicate requirement IDs found."
            )

        # Requirements must be allocated in creation-date order.
        df = df.sort_values(
            by=["created_at", "requirement_id"],
        ).reset_index(drop=True)

        results = []

        for _, requirement in df.iterrows():

            result = self.allocate_one_requirement(
                requirement
            )

            results.append(result)

        return pd.DataFrame(results)

    # =============================================
    # 5. CONTRACT BALANCE SUMMARY
    # =============================================

    def get_contract_balance_summary(self):

        summary = self.contract_balances.copy()

        summary["utilization_pct"] = (
            summary["consumed_value"]
            / summary["value_cap"].replace(0, pd.NA)
            * 100
        )

        return summary.sort_values(
            by="remaining_value",
        ).reset_index(drop=True)
