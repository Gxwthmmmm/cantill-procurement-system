
import pandas as pd


class SupplierRecommendationService:

    def __init__(
        self,
        supplier_service,
        supplier_master,
        po_history,
        contract_lines,
        contract_register,
        item_master
    ):
        self.supplier_service = supplier_service

        self.suppliers = supplier_master.copy()
        self.po_history = po_history.copy()
        self.contract_lines = contract_lines.copy()
        self.contracts = contract_register.copy()
        self.items = item_master.copy()

        self.po_history["po_date"] = pd.to_datetime(
            self.po_history["po_date"],
            errors="coerce"
        )

        self.contracts["start_date"] = pd.to_datetime(
            self.contracts["start_date"],
            errors="coerce"
        )

        self.contracts["end_date"] = pd.to_datetime(
            self.contracts["end_date"],
            errors="coerce"
        )

    # =================================================
    # 1. GET REFERENCE PRICE
    # =================================================

    def get_reference_price(
        self,
        supplier_id,
        item_code,
        calculation_date
    ):

        calculation_date = pd.Timestamp(calculation_date)

        cutoff_date = (
            calculation_date - pd.Timedelta(days=548)
        )

        # ---------------------------------------------
        # FIRST PRIORITY: MOST RECENT PO WITHIN 548 DAYS
        # ---------------------------------------------

        recent_pos = self.po_history[
            (self.po_history["supplier_id"] == supplier_id)
            & (self.po_history["item_code"] == item_code)
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

            return {
                "reference_price": float(latest_po["unit_price"]),
                "price_source": "RECENT_PO",
                "po_number": latest_po["po_number"],
                "contract_id": None
            }

        # ---------------------------------------------
        # SECOND PRIORITY: MOST RECENT CONTRACT RATE
        # ---------------------------------------------

        supplier_contract_lines = self.contract_lines[
            self.contract_lines["item_code"] == item_code
        ].merge(
            self.contracts,
            on="contract_id",
            how="inner"
        )

        supplier_contract_lines = supplier_contract_lines[
            (supplier_contract_lines["supplier_id"] == supplier_id)
            & supplier_contract_lines["start_date"].notna()
            & (supplier_contract_lines["start_date"] <= calculation_date)
        ].copy()

        if not supplier_contract_lines.empty:

            supplier_contract_lines["rate"] = pd.to_numeric(
                supplier_contract_lines["rate"],
                errors="coerce"
            )

            supplier_contract_lines = supplier_contract_lines[
                supplier_contract_lines["rate"].notna()
                & (supplier_contract_lines["rate"] > 0)
            ]

        if not supplier_contract_lines.empty:

            latest_contract = supplier_contract_lines.sort_values(
                "start_date",
                ascending=False
            ).iloc[0]

            return {
                "reference_price": float(latest_contract["rate"]),
                "price_source": "CONTRACT_RATE",
                "po_number": None,
                "contract_id": latest_contract["contract_id"]
            }

        return {
            "reference_price": None,
            "price_source": "NO_REFERENCE_PRICE",
            "po_number": None,
            "contract_id": None
        }

    # =================================================
    # 2. GET ACTIVE CATEGORY SUPPLIERS
    # =================================================

    def get_category_suppliers(self, category):

        active = self.suppliers[
            self.suppliers["status"]
            .astype(str)
            .str.upper()
            .eq("ACTIVE")
        ].copy()

        if category:

            active = active[
                active["categories"]
                .fillna("")
                .astype(str)
                .str.contains(
                    str(category),
                    case=False,
                    regex=False
                )
            ]

        active["on_time_pct"] = pd.to_numeric(
            active["on_time_pct"],
            errors="coerce"
        ).fillna(0)

        active["quality_rating"] = pd.to_numeric(
            active["quality_rating"],
            errors="coerce"
        ).fillna(0)

        return active.sort_values(
            by=["on_time_pct", "quality_rating"],
            ascending=False
        ).reset_index(drop=True)

    # =================================================
    # 3. GENERATE SUPPLIER RECOMMENDATIONS
    # =================================================

    def recommend_suppliers(
        self,
        item_code,
        category,
        calculation_date,
        supplier_count=3,
        is_new_item=False
    ):

        calculation_date = pd.Timestamp(calculation_date)

        # ---------------------------------------------
        # NEW ITEMS CANNOT RECEIVE SUPPLIER SUGGESTIONS
        # ---------------------------------------------

        if (
            is_new_item
            or item_code is None
            or pd.isna(item_code)
            or str(item_code).strip() == ""
        ):

            return {
                "status": "NEW_ITEM_NO_SUPPLIER_SUGGESTIONS",
                "item_code": item_code,
                "category": category,
                "supplier_count_requested": 0,
                "supplier_count_returned": 0,
                "suppliers": []
            }

        if item_code not in set(self.items["item_code"]):

            return {
                "status": "UNKNOWN_ITEM",
                "item_code": item_code,
                "category": category,
                "supplier_count_requested": supplier_count,
                "supplier_count_returned": 0,
                "suppliers": []
            }

        if supplier_count not in (3, 5):
            raise ValueError(
                "Supplier count must be 3 for RFQ or 5 for RFP."
            )

        # ---------------------------------------------
        # GET ELIGIBLE SUPPLIERS
        # ---------------------------------------------

        eligible = self.supplier_service.get_eligible_suppliers(
            category=category,
            calculation_date=calculation_date
        )

        ranked = self.supplier_service.rank_suppliers(
            eligible_suppliers=eligible,
            calculation_date=calculation_date,
            category=category
        )

        selected = []

        # ---------------------------------------------
        # ADD RANKED ELIGIBLE SUPPLIERS FIRST
        # ---------------------------------------------

        for _, supplier in ranked.head(supplier_count).iterrows():

            supplier_id = supplier["supplier_id"]

            price = self.get_reference_price(
                supplier_id=supplier_id,
                item_code=item_code,
                calculation_date=calculation_date
            )

            selected.append({
                "supplier_id": supplier_id,
                "supplier_name": supplier["name"],
                "ranking_score": float(supplier["ranking_score"]),
                "recommendation_source": "RANKED_ELIGIBLE_SUPPLIER",
                **price
            })

        selected_ids = {
            supplier["supplier_id"]
            for supplier in selected
        }

        # ---------------------------------------------
        # SUPPLEMENT WITH ACTIVE CATEGORY SUPPLIERS
        # ---------------------------------------------

        if len(selected) < supplier_count:

            category_suppliers = self.get_category_suppliers(
                category
            )

            for _, supplier in category_suppliers.iterrows():

                supplier_id = supplier["supplier_id"]

                if supplier_id in selected_ids:
                    continue

                price = self.get_reference_price(
                    supplier_id=supplier_id,
                    item_code=item_code,
                    calculation_date=calculation_date
                )

                selected.append({
                    "supplier_id": supplier_id,
                    "supplier_name": supplier["name"],
                    "ranking_score": None,
                    "recommendation_source": "CATEGORY_SUPPLEMENT",
                    "on_time_pct": float(supplier["on_time_pct"]),
                    "quality_rating": float(supplier["quality_rating"]),
                    **price
                })

                selected_ids.add(supplier_id)

                if len(selected) >= supplier_count:
                    break

        # ---------------------------------------------
        # FINAL RESPONSE
        # ---------------------------------------------

        for index, supplier in enumerate(selected, start=1):
            supplier["supplier_rank"] = index

        return {
            "status": (
                "SUCCESS"
                if len(selected) == supplier_count
                else "INSUFFICIENT_SUPPLIERS"
            ),
            "item_code": item_code,
            "category": category,
            "supplier_count_requested": supplier_count,
            "supplier_count_returned": len(selected),
            "suppliers": selected
        }
