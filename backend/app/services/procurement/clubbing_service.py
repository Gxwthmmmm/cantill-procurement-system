
import pandas as pd


class RequirementClubbingService:
    """
    Groups compatible purchase request lines into requirements
    according to the active procurement policy.
    """

    REQUIRED_COLUMNS = {
        "pr_no",
        "pr_line",
        "created_at",
        "plant",
        "item_code",
        "need_by_date",
        "quantity",
        "urgency",
    }

    def __init__(self, policy_data):

        clubbing_policy = policy_data.get("clubbing", {})

        self.creation_window_days = int(
            clubbing_policy.get("creation_window_calendar_days", 14)
        )

        self.need_by_window_days = int(
            clubbing_policy.get("need_by_window_days_each_side", 7)
        )

        self.same_fields = clubbing_policy.get(
            "same_fields",
            ["item_code", "plant"]
        )

        self.sort_by = clubbing_policy.get(
            "sort_by",
            ["created_at", "pr_no", "pr_line"]
        )

        self.multiple_match = clubbing_policy.get(
            "multiple_match",
            "earliest_requirement"
        )

        self.emergency_propagates = bool(
            clubbing_policy.get("emergency_propagates", True)
        )

        if self.same_fields != ["item_code", "plant"]:
            raise ValueError(
                "Unsupported clubbing fields in procurement policy."
            )

        if self.multiple_match != "earliest_requirement":
            raise ValueError(
                "Unsupported multiple-match policy."
            )

    # --------------------------------------------------
    # 1. VALIDATE INPUT
    # --------------------------------------------------

    def _validate_input(self, requests):

        missing_columns = (
            self.REQUIRED_COLUMNS - set(requests.columns)
        )

        if missing_columns:
            raise ValueError(
                f"Missing required columns: {sorted(missing_columns)}"
            )

    # --------------------------------------------------
    # 2. CHECK WHETHER A LINE CAN JOIN A REQUIREMENT
    # --------------------------------------------------

    def _can_join(self, request, requirement):

        if request["item_code"] != requirement["item_code"]:
            return False

        if request["plant"] != requirement["plant"]:
            return False

        creation_difference = (
            request["created_at"] - requirement["created_at"]
        ).days

        if not (
            0 <= creation_difference <= self.creation_window_days
        ):
            return False

        need_by_difference = abs(
            (request["need_by_date"] - requirement["need_by_date"]).days
        )

        if need_by_difference > self.need_by_window_days:
            return False

        return True

    # --------------------------------------------------
    # 3. CHECK EMERGENCY STATUS
    # --------------------------------------------------

    @staticmethod
    def _is_emergency(urgency):

        return (
            str(urgency).strip().casefold() == "emergency"
        )

    # --------------------------------------------------
    # 4. CLUB REQUIREMENTS
    # --------------------------------------------------

    def club_requirements(self, requests):

        self._validate_input(requests)

        df = requests.copy()

        # Convert dates
        df["created_at"] = pd.to_datetime(
            df["created_at"],
            errors="coerce"
        )

        df["need_by_date"] = pd.to_datetime(
            df["need_by_date"],
            errors="coerce"
        )

        # Validate essential fields
        if df["created_at"].isna().any():
            raise ValueError(
                "Some purchase request lines have invalid created_at dates."
            )

        if df["need_by_date"].isna().any():
            raise ValueError(
                "Some purchase request lines have invalid need_by_date dates."
            )

        if df["pr_no"].isna().any() or df["pr_line"].isna().any():
            raise ValueError(
                "Purchase request number and line number cannot be missing."
            )

        # Sort by policy order
        df = df.sort_values(
            by=self.sort_by
        ).reset_index(drop=True)

        # Internal requirement groups
        requirements = []

        line_assignments = {}

        for index, request in df.iterrows():

            item_code = request["item_code"]

            # Missing item code means new/unmatched item.
            # New items must never be clubbed.
            is_new_item = (
                pd.isna(item_code)
                or str(item_code).strip() == ""
            )

            if is_new_item:

                requirement = {
                    "requirement_id": f"REQ-{len(requirements) + 1:05d}",
                    "item_code": None,
                    "plant": request["plant"],
                    "created_at": request["created_at"],
                    "need_by_date": request["need_by_date"],
                    "indices": [index],
                    "is_new_item": True,
                    "is_emergency": self._is_emergency(
                        request["urgency"]
                    ),
                }

                requirements.append(requirement)

                line_assignments[index] = requirement["requirement_id"]

                continue

            # Find all existing requirements that qualify.
            matching_requirements = [
                requirement
                for requirement in requirements
                if not requirement["is_new_item"]
                and self._can_join(request, requirement)
            ]

            if matching_requirements:

                # Requirements are created in chronological order.
                # Select the earliest qualifying requirement.
                selected = min(
                    matching_requirements,
                    key=lambda requirement: (
                        requirement["created_at"],
                        requirement["requirement_id"]
                    )
                )

                selected["indices"].append(index)

                if (
                    self.emergency_propagates
                    and self._is_emergency(request["urgency"])
                ):
                    selected["is_emergency"] = True

                line_assignments[index] = selected["requirement_id"]

            else:

                requirement = {
                    "requirement_id": f"REQ-{len(requirements) + 1:05d}",
                    "item_code": item_code,
                    "plant": request["plant"],
                    "created_at": request["created_at"],
                    "need_by_date": request["need_by_date"],
                    "indices": [index],
                    "is_new_item": False,
                    "is_emergency": self._is_emergency(
                        request["urgency"]
                    ),
                }

                requirements.append(requirement)

                line_assignments[index] = requirement["requirement_id"]

        # --------------------------------------------------
        # 5. BUILD OUTPUT
        # --------------------------------------------------

        df["requirement_id"] = df.index.map(line_assignments)

        requirement_details = {}

        for requirement in requirements:

            requirement_details[requirement["requirement_id"]] = {
                "requirement_created_at": requirement["created_at"],
                "requirement_need_by_date": requirement["need_by_date"],
                "is_new_item_requirement": requirement["is_new_item"],
                "is_emergency_requirement": requirement["is_emergency"],
                "requirement_line_count": len(requirement["indices"]),
            }

        details_df = pd.DataFrame.from_dict(
            requirement_details,
            orient="index"
        )

        details_df.index.name = "requirement_id"

        df = df.merge(
            details_df.reset_index(),
            on="requirement_id",
            how="left"
        )

        # Emergency propagation applies to the complete requirement.
        if self.emergency_propagates:
            df["requirement_urgency"] = df[
                "is_emergency_requirement"
            ].map({
                True: "Emergency",
                False: "Normal"
            })

        return df.reset_index(drop=True)

    # --------------------------------------------------
    # 6. REQUIREMENT SUMMARY
    # --------------------------------------------------

    def get_requirement_summary(self, clubbed_requests):

        summary = (
            clubbed_requests
            .groupby("requirement_id", as_index=False)
            .agg(
                item_code=("item_code", "first"),
                plant=("plant", "first"),
                line_count=("pr_line", "count"),
                total_quantity=("quantity", "sum"),
                is_new_item=("is_new_item_requirement", "first"),
                is_emergency=("is_emergency_requirement", "first"),
                created_at=("requirement_created_at", "first"),
                need_by_date=("requirement_need_by_date", "first"),
            )
        )

        return summary
