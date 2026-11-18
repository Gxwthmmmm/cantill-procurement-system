import json
from pathlib import Path
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import PolicyVersion

POLICY = {
  "document_id": "CORVO-PROC-POL-04",
  "version": "5.0",
  "effective_date": "2026-04-01",
  "owner": "Head of Procurement",
  "plants": ["PUN1", "CHK1"],
  "currency": "INR",
  "rules": [
    {"id":"1.2","priority":10,"when":{"item_match":"NEW"},"then":{"decision":"SOURCING_REQUEST","route":"NEW_ITEM_SOURCING","supplier_count":0,"never_club":True,"valuation":"quantity_times_requester_estimate"}},
    {"id":"5.1","priority":20,"when":{"item_type":"Capex"},"then":{"decision":"SOURCING_REQUEST","route":"CAPEX_SOURCING","supplier_count":5,"requires_capex_approval":True}},
    {"id":"5.2","priority":30,"when":{"usable_contract":True},"then":{"decision":"PO","route":"CONTRACT_PO","supplier":"contract_supplier","price":"contract_rate"}},
    {"id":"5.3","priority":40,"when":{"urgency":"Emergency","max_value_inr":500000,"purchased_from_active_supplier_within_days":365},"then":{"decision":"PO","route":"EMERGENCY_PO","supplier":"preferred_supplier_1","price":"preferred_reference_price"}},
    {"id":"5.4","priority":50,"when":{"max_value_exclusive_inr":200000,"purchased_from_active_supplier_within_days":365},"then":{"decision":"PO","route":"SPOT_PO","supplier":"preferred_supplier_1","price":"preferred_reference_price"}},
    {"id":"5.5","priority":60,"when":{"max_value_exclusive_inr":1000000},"then":{"decision":"SOURCING_REQUEST","route":"RFQ","supplier_count":3}},
    {"id":"5.6","priority":70,"when":{"min_value_inclusive_inr":1000000},"then":{"decision":"SOURCING_REQUEST","route":"RFP","supplier_count":5}}
  ],
  "clubbing":{"rule_id":"2.2","creation_window_calendar_days":14,"need_by_window_days_each_side":7,"same_fields":["item_code","plant"],"sort_by":["created_at","pr_no","pr_line"],"multiple_match":"earliest_requirement","emergency_propagates":True},
  "valuation":{"rule_id":"3.1","quantity_times_unit_price":True,"unit_price_priority":["usable_contract_rate","lowest_applicable_contract_rate_if_all_out_of_ceiling","most_recent_po_within_365_days","item_master_standard_price"]},
  "contracts":{"rule_ids":["4.1","4.2","4.3"],"active_supplier_only":True,"validity_inclusive":True,"ceiling_check":"consumed_value_plus_requirement_at_contract_rate_lte_value_cap","allocation_order":"requirement_date","post_register_contract_initial_consumed_value":0,"select":"lowest_rate_with_sufficient_ceiling"},
  "suppliers":{"rule_ids":["6.1","6.2","6.3","6.4"],"po_lookback_days":548,"ranking_factors":["purchase_frequency","purchase_recency","contract_history","on_time_delivery","quality"],"reference_price_priority":["most_recent_po_within_548_days","most_recent_contract_rate"],"exclude_statuses":["Blocked","Inactive"],"sourcing_supplement":"active_suppliers_in_item_category_by_delivery_then_quality","new_item_suggestions":False},
  "po_consolidation":{"rule_id":"7.1","same_fields":["supplier_id","plant","route"],"first_requirement_window_hours":24,"sort_by":"requirement_creation_time","sourcing_requests_consolidated":False},
  "record_keeping":{"rule_id":"8.1","store_policy_clause":True,"store_contract_or_po_evidence":True,"override_requires_written_reason":True}
}

def main():
    db=SessionLocal()
    try:
        existing=db.scalar(select(PolicyVersion).where(PolicyVersion.version=="5.0"))
        if not existing:
            db.add(PolicyVersion(version="5.0", effective_date="2026-04-01", status="active", source_document="Corvo_Procurement_Policy.pdf", policy_data=POLICY, change_summary="Initial import of Corvo Procurement Policy v5.0"))
            db.commit()
            print("Seeded active policy v5.0")
        else: print("Policy v5.0 already exists; leaving it unchanged")
    finally: db.close()

if __name__=="__main__": main()
