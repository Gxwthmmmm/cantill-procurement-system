
import pandas as pd


class ProcurementValuator:

    def __init__(
        self,
        contract_lines,
        contract_register,
        po_history,
        item_master,
        supplier_master=None
    ):
        self.contract_lines = contract_lines.copy()
        self.contract_register = contract_register.copy()
        self.po_history = po_history.copy()
        self.item_master = item_master.copy()

        self.suppliers = (
            supplier_master.copy()
            if supplier_master is not None
            else None
        )

        # Convert dates safely
        self.contract_register["start_date"] = pd.to_datetime(
            self.contract_register["start_date"],
            errors="coerce"
        )

        self.contract_register["end_date"] = pd.to_datetime(
            self.contract_register["end_date"],
            errors="coerce"
        )

        self.po_history["po_date"] = pd.to_datetime(
            self.po_history["po_date"],
            errors="coerce"
        )

    def value_request(
        self,
        item_code,
        quantity,
        calculation_date,
        estimated_unit_price=None
    ):

        calculation_date = pd.Timestamp(calculation_date)

        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            return {
                "status": "INVALID_QUANTITY",
                "unit_price": None,
                "total_value": None,
                "source": None
            }

        if not pd.notna(quantity) or quantity <= 0:
            return {
                "status": "INVALID_QUANTITY",
                "unit_price": None,
                "total_value": None,
                "source": None
            }

        # ---------------------------------------------
        # 1. NEW ITEM VALUATION
        # ---------------------------------------------

        if item_code is None or pd.isna(item_code) or str(item_code).strip() == "":

            if (
                estimated_unit_price is None
                or pd.isna(estimated_unit_price)
            ):
                return {
                    "status": "MISSING_ESTIMATED_PRICE",
                    "unit_price": None,
                    "total_value": None,
                    "source": None
                }

            try:
                unit_price = float(estimated_unit_price)
            except (TypeError, ValueError):
                return {
                    "status": "INVALID_ESTIMATED_PRICE",
                    "unit_price": None,
                    "total_value": None,
                    "source": None
                }

            if not pd.notna(unit_price) or unit_price <= 0:
                return {
                    "status": "INVALID_ESTIMATED_PRICE",
                    "unit_price": None,
                    "total_value": None,
                    "source": None
                }

            return {
                "status": "VALUED",
                "unit_price": unit_price,
                "total_value": unit_price * quantity,
                "source": "ESTIMATED_PRICE"
            }

        # ---------------------------------------------
        # 2. VALIDATE ITEM
        # ---------------------------------------------

        item = self.item_master[
            self.item_master["item_code"] == item_code
        ]

        if item.empty:
            return {
                "status": "UNKNOWN_ITEM",
                "unit_price": None,
                "total_value": None,
                "source": None
            }

        # ---------------------------------------------
        # 3. FIND APPLICABLE CONTRACTS
        # ---------------------------------------------

        lines = self.contract_lines[
            self.contract_lines["item_code"] == item_code
        ]

        contracts = lines.merge(
            self.contract_register,
            on="contract_id",
            how="inner"
        )

        contracts = contracts[
            contracts["start_date"].notna()
            & contracts["end_date"].notna()
            & (contracts["start_date"] <= calculation_date)
            & (contracts["end_date"] >= calculation_date)
        ].copy()

        # Only active suppliers can provide a usable contract PO.
        # Keep all applicable contract rates for fallback valuation.
        if not contracts.empty and self.suppliers is not None:

            active_supplier_ids = set(
                self.suppliers.loc[
                    self.suppliers["status"]
                    .astype(str)
                    .str.upper()
                    .eq("ACTIVE"),
                    "supplier_id"
                ]
            )

            contracts["active_supplier"] = (
                contracts["supplier_id"].isin(active_supplier_ids)
            )

        else:
            contracts["active_supplier"] = True

        if not contracts.empty:

            contracts["rate"] = pd.to_numeric(
                contracts["rate"],
                errors="coerce"
            )

            contracts["value_cap"] = pd.to_numeric(
                contracts["value_cap"],
                errors="coerce"
            )

            contracts["consumed_value"] = pd.to_numeric(
                contracts["consumed_value"],
                errors="coerce"
            )

            contracts = contracts[
                contracts["rate"].notna()
                & (contracts["rate"] > 0)
                & contracts["value_cap"].notna()
                & contracts["consumed_value"].notna()
            ].copy()

            contracts["remaining_value"] = (
                contracts["value_cap"]
                - contracts["consumed_value"]
            )

        # ---------------------------------------------
        # 4. SELECT USABLE CONTRACT
        # ---------------------------------------------

        if not contracts.empty:

            usable = contracts[
                contracts["active_supplier"]
                & (
                    contracts["remaining_value"]
                    >= contracts["rate"] * quantity
                )
            ].copy()

            if not usable.empty:

                selected = usable.sort_values(
                    by="rate",
                    ascending=True
                ).iloc[0]

                unit_price = float(selected["rate"])

                return {
                    "status": "VALUED",
                    "unit_price": unit_price,
                    "total_value": unit_price * quantity,
                    "source": "CONTRACT_RATE",
                    "contract_id": selected["contract_id"],
                    "supplier_id": selected["supplier_id"]
                }

            # -----------------------------------------
            # 5. LOWEST APPLICABLE CONTRACT RATE
            # WHEN ALL CONTRACTS ARE OUT OF CEILING
            # -----------------------------------------

            fallback_contracts = contracts[
                contracts["active_supplier"]
            ]

            if not fallback_contracts.empty:

                selected = fallback_contracts.sort_values(
                    by="rate",
                    ascending=True
                ).iloc[0]

                unit_price = float(selected["rate"])

                return {
                    "status": "VALUED",
                    "unit_price": unit_price,
                    "total_value": unit_price * quantity,
                    "source": "LOWEST_APPLICABLE_CONTRACT_RATE",
                    "contract_id": selected["contract_id"],
                    "supplier_id": selected["supplier_id"],
                    "warning": (
                        "No applicable active-supplier contract "
                        "has sufficient remaining ceiling."
                    )
                }

        # ---------------------------------------------
        # 6. MOST RECENT PO WITHIN 365 DAYS
        # ---------------------------------------------

        cutoff_date = (
            calculation_date - pd.Timedelta(days=365)
        )

        recent_pos = self.po_history[
            (self.po_history["item_code"] == item_code)
            & (self.po_history["po_date"] >= cutoff_date)
            & (self.po_history["po_date"] <= calculation_date)
        ].copy()

        if not recent_pos.empty:

            recent_pos["unit_price"] = pd.to_numeric(
                recent_pos["unit_price"],
                errors="coerce"
            )

            recent_pos = recent_pos[
                recent_pos["unit_price"].notna()
                & (recent_pos["unit_price"] > 0)
            ]

        if not recent_pos.empty:

            latest_po = recent_pos.sort_values(
                "po_date",
                ascending=False
            ).iloc[0]

            unit_price = float(latest_po["unit_price"])

            return {
                "status": "VALUED",
                "unit_price": unit_price,
                "total_value": unit_price * quantity,
                "source": "RECENT_PO_PRICE",
                "po_number": latest_po["po_number"]
            }

        # ---------------------------------------------
        # 7. ITEM MASTER STANDARD PRICE
        # ---------------------------------------------

        standard_price = item.iloc[0]["standard_price"]

        if pd.notna(standard_price):

            unit_price = float(standard_price)

            if unit_price > 0:

                return {
                    "status": "VALUED",
                    "unit_price": unit_price,
                    "total_value": unit_price * quantity,
                    "source": "STANDARD_PRICE"
                }

        return {
            "status": "MISSING_PRICE",
            "unit_price": None,
            "total_value": None,
            "source": None
        }
