
import pandas as pd


class ProcurementValidator:

    def __init__(self, item_master, plants):
        self.items = item_master.copy()
        self.plants = plants.copy()

        self.valid_item_codes = set(
            self.items["item_code"].dropna().astype(str)
        )

        self.valid_plants = set(
            self.plants["plant"].dropna().astype(str)
        )

    def validate_plant(self, plant):
        if pd.isna(plant) or str(plant).strip() not in self.valid_plants:
            return {
                "valid": False,
                "status": "INVALID_PLANT",
                "message": f"Plant '{plant}' is not registered."
            }

        return {
            "valid": True,
            "status": "VALID",
            "message": "Plant validated successfully."
        }

    def validate_item_code(self, item_code):
        if pd.isna(item_code) or str(item_code).strip() == "":
            return {
                "valid": False,
                "status": "MISSING_ITEM_CODE",
                "message": "Item code is missing."
            }

        if str(item_code).strip() not in self.valid_item_codes:
            return {
                "valid": False,
                "status": "UNKNOWN_ITEM_CODE",
                "message": f"Item code '{item_code}' is not in the item master."
            }

        return {
            "valid": True,
            "status": "VALID",
            "message": "Item code validated successfully."
        }

    def validate_request(self, request):
        plant_result = self.validate_plant(request.get("plant"))
        item_result = self.validate_item_code(request.get("item_code"))

        errors = []

        if not plant_result["valid"]:
            errors.append(plant_result)

        if not item_result["valid"]:
            errors.append(item_result)

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
