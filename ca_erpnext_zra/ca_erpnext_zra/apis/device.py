import frappe
from .api_processor import process_request
from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME

@frappe.whitelist()
def initialize_device(request_data: str) -> None:
    """
    Initialize a device with Crystal VSDC servers.

    Args:
        request_data (str): JSON string containing device details.
    """
    return process_request(
        request_data=request_data,
        route_key="",  # Crystal-specific route key
        handler_function=initialize_device_on_success,
        request_method="POST",
        doctype=SETTINGS_DOCTYPE_NAME,
    )


def initialize_device_on_success(response: dict) -> dict:
    """
    Handle a successful device initialization response from Crystal VSDC.
    """
    frappe.msgprint("Device initialization successful with Crystal VSDC.")
    return response
