import frappe
import json
import frappe
from ..services.code_list_service import (sync_item_codes, sync_vsdc_codes)






@frappe.whitelist()
def refresh_vsdc_codes(settings_name: str, last_req_dt: str = None) -> dict:
    """
    Fetch and update all code lists (currencies, packaging units, taxation, etc.)
    from Crystal VSDC using the SelectCodes endpoint.
    """
    return sync_vsdc_codes(settings_name=settings_name, last_req_dt=last_req_dt)




@frappe.whitelist()
def get_item_classification_codes(settings_name: str, LastReqDt: str = None) -> str:
    """Fetch item classification codes  from ZRA VSDC."""
    return sync_item_codes(settings_name=settings_name,LastReqDt=LastReqDt)