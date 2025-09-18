import frappe
from .api_processor import process_request
from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME


@frappe.whitelist()
def initialize_device(request_data: str | dict, settings_name: str = None) -> dict:
    """
    Initialize a device with Crystal VSDC servers.

    Endpoint:
        POST /api/v1/InitializationInfo/SelectInitInfo

    Args:
        request_data (str | dict): JSON string or dict with keys:
            - tpin (str): Taxpayer Identification Number
            - bhfId (str): Branch ID
            - dvcSrlNo (str): Device Serial Number
        settings_name (str, optional): Crystal ZRA Smart Invoice Settings docname.

    Returns:
        dict: Response from Crystal VSDC.
    """
    return process_request(
        request_data=request_data,
        route_key="InitializationInfo/SelectInitInfo",
        handler_function=initialize_device_on_success,
        request_method="POST",
        doctype=SETTINGS_DOCTYPE_NAME,
        settings_name=settings_name,
    )


def initialize_device_on_success(response: dict, **kwargs) -> dict:
    """
    Handle a successful device initialization response from Crystal VSDC.
    Stores API keys if returned.
    """
    if response.get("message") == "Device already installed":
        frappe.msgprint("ℹ️ Device already initialized with Crystal VSDC.")
    else:
        frappe.msgprint("✅ Device initialization successful with Crystal VSDC.")

    # Save API keys to settings if available
    # api_key = response.get("apiKey")
    # secret_key = response.get("secretKey")

    # if api_key and secret_key:
    #     settings_name = kwargs.get("settings_name")
    #     if settings_name:
    #         settings = frappe.get_doc(SETTINGS_DOCTYPE_NAME, settings_name)
    #         settings.db_set("api_key", api_key)
    #         settings.db_set("secret_key", secret_key)

    return response
