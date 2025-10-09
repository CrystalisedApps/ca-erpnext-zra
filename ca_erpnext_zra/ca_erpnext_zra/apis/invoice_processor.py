import frappe
from frappe.utils.password import get_decrypted_password
from frappe.utils import now_datetime
from ..utils.payload_utils import build_invoice_payload, build_credit_note_payload  # keep payload logic modular
from ..handlers.invoice_handler import update_invoice_info

def _process_vsdc_invoice_request(
    document_name: str,
    invoice_type: str = "Sales Invoice",
    settings_name: str = None,
    company: str = None,
    handler_function=None,
    is_return: bool = False,
) -> None:
    """
    Common helper to process Crystal VSDC (ZRA Smart Invoice) requests
    for Sales Invoices or Credit Notes.
    """
    invoice = frappe.get_doc(invoice_type, document_name)
    settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)

    # Pick correct API endpoint
    endpoint = "/saveSales"
    if is_return or getattr(invoice, "is_return", False):
        endpoint = "/saveSalesReturn"

    # Build payload dynamically
    if is_return:
        payload = build_credit_note_payload(invoice, settings_name)
    else:
        payload = build_invoice_payload(invoice, settings_name)

    try:
        # Send to ZRA VSDC
        response = send_vsdc_request(endpoint, payload, settings)
        status_code = response.get("StatusCode")
        is_success = response.get("IsSuccess")

        if not is_success:
            frappe.throw(f"ZRA Error: {response.get('ErrorMessage', 'Unknown error')}")

        # Optional callback for handling post-processing
        if handler_function:
            handler_function(invoice, response)

        frappe.msgprint(f"Successfully sent invoice to ZRA Smart Invoice (Ref: {invoice.name})")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Crystal VSDC Invoice Submission Failed")
        frappe.throw(f"Failed to process ZRA request: {e}")

@frappe.whitelist()
def get_vsdc_invoice_details(
    document_name: str,
    invoice_type: str = "Sales Invoice",
    settings_name: str = None,
    company: str = None,
):
    """
    Fetch and refresh Crystal VSDC (ZRA Smart Invoice) details for a Sales Invoice,
    using the centralized `process_request` API wrapper.
    """
    from ca_erpnext_zra.ca_erpnext_zra.apis.api_processor import process_request

    # Fetch invoice
    invoice = frappe.get_doc(invoice_type, document_name)

    # Fetch first active settings record
    settings = frappe.get_all(
        "Crystal ZRA Smart Invoice Settings",
        fields=["name"],
        filters={"is_active": 1},
        limit=1
    )

    if not settings:
        frappe.throw("No active Crystal ZRA Smart Invoice Settings found.")

    settings_name = settings[0]["name"]
    settings_doc = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)

    # Decrypt TPIN
  
    tpin = (
        get_decrypted_password("Crystal ZRA Smart Invoice Settings", settings_name, "tpin", raise_exception=False)
        or ""
    )

    # Build payload
    payload = {
        "tpin": tpin,
        "bhfId": "000",
        "CisInvcNo": invoice.name,
    }

    # Define success handler for response
    def on_success(response, **_):
        if not response:
            frappe.throw("Empty response from ZRA Smart Invoice system.")
        if not response.get("IsSuccess"):
            frappe.throw(f"ZRA Error: {response.get('ErrorMessage', 'Unknown error')}")

        update_invoice_info(
        response=response,
        document_name=invoice.name,
        doctype=invoice.doctype,
)

        frappe.msgprint(f"Invoice details synced successfully with ZRA for {invoice.name}")

    # Define error handler
    def on_error(error):
        frappe.log_error(
            title="VSDC API Error",
            message=f"Failed to fetch VSDC invoice details: {error}"
        )

    # Use process_request to send the request
    process_request(
        request_data=payload,
        route_key="SelectInvoice",  # or endpoint name as defined in your API builder
        handler_function=on_success,
        request_method="POST",
        doctype=invoice_type,
        settings_name=settings_name,
        company=company or invoice.company,
        error_callback=on_error,
     
        document_name=document_name,
    )