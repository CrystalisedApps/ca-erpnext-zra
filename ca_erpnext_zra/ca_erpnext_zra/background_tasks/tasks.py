import frappe
from ..apis.api_processor import process_request
# from ..apis.api_builder import EndpointsBuilder
# from ..utils import settings_utils
from ..services.code_list_service import (update_currencies,
                                          update_packaging_units,
                                          update_taxation_type,
                                          update_item_classification_codes,
                                          update_unit_of_quantity)

@frappe.whitelist()
def refresh_code_lists(settings_name: str, request_data: dict) -> str:
    """Fetch and update ZRA code lists (currencies, packaging, UOM, taxation)."""
    tasks = [
        ("CurrencySearchReq", update_currencies),
        ("PackagingUnitSearchReq", update_packaging_units),
        ("QuantityUnitsSearchReq", update_unit_of_quantity),
        ("TaxSearchReq", update_taxation_type),
    ]

    results = []
    for task in tasks:
        results.append(
            process_request(request_data, task[0], task[1], settings_name=settings_name)
        )
    return results

@frappe.whitelist()
def get_item_classification_codes(settings_name: str, request_data: dict) -> str:
    """Fetch item classification codes (HS/Tariff) from ZRA VSDC."""
    return process_request(
        request_data,
        "ItemClsSearchReq",
        update_item_classification_codes,
        settings_name=settings_name,
    )
