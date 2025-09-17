import frappe
from frappe import _
from frappe.utils.background_jobs import enqueue

from .api_processor import process_request
from ..services.code_list_service import (
    update_countries,
    update_currencies,
    update_packaging_units,
    update_unit_of_quantity,
    update_taxation_type,
)

@frappe.whitelist()
def refresh_code_lists(request_data: str | dict, settings_name: str) -> str:
    """Refresh code lists from Crystal VSDC based on request data."""
    tasks = [
        ("GetCountries", update_countries),
        ("GetCurrencies", update_currencies),
        ("GetPackagingUnits", update_packaging_units),
        ("GetQuantityUnits", update_unit_of_quantity),
        ("GetTaxTypes", update_taxation_type),
    ]

    messages = []

    for route_key, success_handler in tasks:
        msg = process_request(
            request_data=request_data,
            route_key=route_key,          # Crystal VSDC endpoint key
            on_success=success_handler,   # Maps response into ERPNext doctypes
            settings_name=settings_name,
        )
        messages.append(msg)

    return messages
