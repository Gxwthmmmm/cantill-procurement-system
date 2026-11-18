
import pandas as pd


class SupplierService:

    REQUIRED_WEIGHT_FACTORS = {
        "purchase_frequency",
        "purchase_recency",
        "contract_history",
        "on_time_delivery",
        "quality",
    }

    def __init__(
        self,
        supplier_master,
        po_history,
        contract_register,
        item_master,
        ranking_weights
    ):
        self.suppliers = supplier_master.copy()
        self.po_history = po_history.copy()
        self.contracts = contract_register.copy()
        self.items = item_master.copy()

        # ---------------------------------------------
        # LOAD AND VALIDATE POLICY RANKING WEIGHTS
        # ---------------------------------------------

        if not ranking_weights:
            raise ValueError(
                "Ranking weights are missing from the active policy."
            )

        if set(ranking_weights.keys()) != self.REQUIRED_WEIGHT_FACTORS:
            raise ValueError(
                "Invalid supplier ranking factors in procurement policy."
            )

        self.ranking_weights = {
            factor: float(weight)
            for factor, weight in ranking_weights.items()
        }

        if any(
            weight < 0 or weight > 1
            for weight in self.ranking_weights.values()
        ):
            raise ValueError(
                "Ranking weights must be between 0 and 1."
            )

        if abs(sum(self.ranking_weights.values()) - 1.0) > 0.000001:
            raise ValueError(
                "Supplier ranking weights must total 100%."
            )

        # ---------------------------------------------
        # DATE CONVERSIONS
        # ---------------------------------------------

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

        # ---------------------------------------------
        # ADD ITEM CATEGORY TO PURCHASE HISTORY
        # ---------------------------------------------

        item_categories = self.items[
            ["item_code", "category"]
        ].drop_duplicates(subset=["item_code"])

        self.po_history = self.po_history.merge(
            item_categories,
            on="item_code",
            how="left"
        )

    # =================================================
    # 1. GET ELIGIBLE SUPPLIERS
    # =================================================

    def get_eligible_suppliers(
        self,
        category,
        calculation_date,
        item_code=None
    ):

        calculation_date = pd.Timestamp(calculation_date)

        cutoff_date = (
            calculation_date - pd.Timedelta(days=548)
        )

        # Only active suppliers are eligible
        eligible = self.suppliers[
            self.suppliers["status"]
            .astype(str)
            .str.upper()
            .eq("ACTIVE")
        ].copy()

        eligible_ids = []

        for _, supplier in eligible.iterrows():

            supplier_id = supplier["supplier_id"]

            # -----------------------------------------
            # RECENT PURCHASE HISTORY
            # -----------------------------------------

            recent_pos = self.po_history[
                (self.po_history["supplier_id"] == supplier_id)
                & (self.po_history["po_date"] >= cutoff_date)
                & (self.po_history["po_date"] <= calculation_date)
            ]

            if item_code:
                recent_pos = recent_pos[
                    recent_pos["item_code"] == item_code
                ]

            # -----------------------------------------
            # CONTRACT ELIGIBILITY
            # -----------------------------------------

            supplier_contracts = self.contracts[
                (self.contracts["supplier_id"] == supplier_id)
                & (self.contracts["start_date"] <= calculation_date)
            ]

            # Supplier qualifies through either:
            # 1. Recent purchase history
            # 2. Contract started on/before calculation date

            if (
                not recent_pos.empty
                or not supplier_contracts.empty
            ):
                eligible_ids.append(supplier_id)

        result = eligible[
            eligible["supplier_id"].isin(eligible_ids)
        ].copy()

        # ---------------------------------------------
        # CATEGORY FILTER
        # ---------------------------------------------

        if category:
            result = result[
                result["categories"]
                .fillna("")
                .astype(str)
                .str.contains(
                    category,
                    case=False,
                    regex=False
                )
            ]

        return result.reset_index(drop=True)

    # =================================================
    # 2. RANK SUPPLIERS
    # =================================================

    def rank_suppliers(
        self,
        eligible_suppliers,
        calculation_date,
        category=None
    ):

        calculation_date = pd.Timestamp(calculation_date)

        cutoff_date = (
            calculation_date - pd.Timedelta(days=548)
        )

        ranked = eligible_suppliers.copy()

        if ranked.empty:
            return ranked

        # ---------------------------------------------
        # A. CATEGORY-AWARE PURCHASE HISTORY
        # ---------------------------------------------

        recent_pos = self.po_history[
            (self.po_history["po_date"] >= cutoff_date)
            & (self.po_history["po_date"] <= calculation_date)
        ].copy()

        if category:
            recent_pos = recent_pos[
                recent_pos["category"]
                .fillna("")
                .astype(str)
                .str.casefold()
                == str(category).casefold()
            ]

        purchase_counts = (
            recent_pos.groupby("supplier_id")
            .size()
        )

        latest_purchases = (
            recent_pos.groupby("supplier_id")["po_date"]
            .max()
        )

        ranked["purchase_frequency"] = (
            ranked["supplier_id"]
            .map(purchase_counts)
            .fillna(0)
        )

        ranked["last_purchase_date"] = (
            ranked["supplier_id"]
            .map(latest_purchases)
        )

        ranked["purchase_recency_days"] = (
            calculation_date - ranked["last_purchase_date"]
        ).dt.days

        ranked["purchase_recency_days"] = (
            ranked["purchase_recency_days"].fillna(548)
        )

        # Purchase frequency score
        ranked["purchase_frequency_score"] = (
            ranked["purchase_frequency"].rank(pct=True)
        )

        # Purchase recency score
        ranked["recency_score"] = (
            1 - ranked["purchase_recency_days"] / 548
        ).clip(0, 1)

        # ---------------------------------------------
        # B. CONTRACT HISTORY
        # ---------------------------------------------

        supplier_contracts = self.contracts[
            self.contracts["start_date"].notna()
            & (self.contracts["start_date"] <= calculation_date)
        ].copy()

        contract_counts = (
            supplier_contracts.groupby("supplier_id")
            .size()
        )

        ranked["contract_count"] = (
            ranked["supplier_id"]
            .map(contract_counts)
            .fillna(0)
        )

        max_contract_count = ranked["contract_count"].max()

        if max_contract_count > 0:

            ranked["contract_history_score"] = (
                ranked["contract_count"] / max_contract_count
            ).clip(0, 1)

        else:
            ranked["contract_history_score"] = 0.0

        # ---------------------------------------------
        # C. DELIVERY PERFORMANCE
        # ---------------------------------------------

        ranked["delivery_score"] = (
            pd.to_numeric(
                ranked["on_time_pct"],
                errors="coerce"
            ).fillna(0) / 100
        ).clip(0, 1)

        # ---------------------------------------------
        # D. QUALITY PERFORMANCE
        # ---------------------------------------------

        ranked["quality_score"] = (
            pd.to_numeric(
                ranked["quality_rating"],
                errors="coerce"
            ).fillna(0) / 5
        ).clip(0, 1)

        # ---------------------------------------------
        # E. POLICY-DRIVEN RANKING SCORE
        # ---------------------------------------------

        weights = self.ranking_weights

        ranked["ranking_score"] = (
            weights["purchase_frequency"]
            * ranked["purchase_frequency_score"]

            + weights["purchase_recency"]
            * ranked["recency_score"]

            + weights["contract_history"]
            * ranked["contract_history_score"]

            + weights["on_time_delivery"]
            * ranked["delivery_score"]

            + weights["quality"]
            * ranked["quality_score"]
        )

        # ---------------------------------------------
        # F. FINAL SORTING
        # ---------------------------------------------

        ranked = ranked.sort_values(
            by="ranking_score",
            ascending=False
        ).reset_index(drop=True)

        ranked["supplier_rank"] = (
            ranked.index + 1
        )

        return ranked
