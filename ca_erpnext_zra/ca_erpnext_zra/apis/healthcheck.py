import frappe
from frappe.model.document import Document

from .api_builder import ZRAEndpointsBuilder

@frappe.whitelist()
def ping_server(settings: Document | str) -> dict | None:
    """Ping the Crystal VSDC server to check connectivity.

    Args:
        settings (Document | str): The Crystal ZRA settings Doc or name of the Doc.

    Returns:
        dict | None: Response from Crystal VSDC API if successful, otherwise None.
    """
    if isinstance(settings, str):
        settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings)

    builder = ZRAEndpointsBuilder()
    builder.settings = settings
    builder.url = f"{settings.server_url}/ping"
    builder.method = "GET"
    builder.headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.jwt}",
    }
    builder.request_description = "Ping Crystal VSDC Server"

    # Callbacks
    def on_success(response, **kwargs):
        frappe.msgprint("Successfully connected to Crystal VSDC server", alert=True)

    def on_error(response, **kwargs):
        frappe.log_error("Failed to connect to Crystal VSDC server", "Ping Server Error")

    builder.success_callback = on_success
    builder.error_callback = on_error

    return builder.make_remote_call(doctype="Crystal ZRA Smart Invoice Settings", document_name=settings.name)
