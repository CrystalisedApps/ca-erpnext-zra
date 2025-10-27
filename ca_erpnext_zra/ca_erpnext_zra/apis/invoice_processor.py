import frappe
from frappe.utils.password import get_decrypted_password
from frappe.utils import now_datetime
from ..utils.payload_utils import build_invoice_payload, build_credit_note_payload  # keep payload logic modular
from ..handlers.invoice_handler import update_invoice_info
from ..handlers.invoice_handler import verify_and_fix_invoice_info
from ca_erpnext_zra.ca_erpnext_zra.apis.api_processor import process_request


@frappe.whitelist()
def _process_vsdc_invoice_request(
    id: str = None,
    document_name: str = None,
    invoice_type: str = "Sales Invoice",
    settings_name: str = None,
    company: str = None,
    handler_function=None,
    reference_number: str = None,
    is_return: bool = False,
    original_invoice_id: str = None,
) -> None:
    """
    Unified helper for Crystal VSDC (ZRA Smart Invoice) requests —
    handles submission, credit note posting, and invoice lookups.
    """
    invoice = frappe.get_doc(invoice_type, document_name)

    # Fetch default settings if not provided
    if not settings_name:
        settings = frappe.get_all(
            "Crystal ZRA Smart Invoice Settings",
            filters={"is_active": 1},
            fields=["name"],
            limit=1,
        )
        if not settings:
            frappe.throw("No active Crystal ZRA Smart Invoice Settings found.")
        settings_name = settings[0]["name"]

    # Base request data
    request_data = {"document_name": document_name, "company": company or invoice.company}

    # Route decision logic
    route_key = "SelectInvoice"  # default: fetch or verify

    if invoice.is_return or is_return:
        route_key = "SaveCreditNote"
    elif not id:
        route_key = "SaveSales"

    # Handle IDs or references
    if id:
        request_data["id"] = id
    elif (invoice.is_return and invoice.return_against) or (is_return and original_invoice_id):
        route_key = "SaveCreditNote"
        original_invoice_slade_id = (
            original_invoice_id
            if is_return
            else frappe.db.get_value("Sales Invoice", invoice.return_against, "custom_slade_id")
        )
        request_data["invoice"] = original_invoice_slade_id
    else:
        route_key = "SaveSales"
        request_data["reference_number"] = reference_number or invoice.name

    # Attach payload if this is a submission route
    if route_key in ["SaveSales", "SaveCreditNote"]:
        payload = (
            build_credit_note_payload(invoice, settings_name)
            if is_return or invoice.is_return
            else build_invoice_payload(invoice, settings_name)
        )
        request_data.update(payload)

    # Delegate to process_request
    return process_request(
        request_data=request_data,
        route_key=route_key,
        handler_function=handler_function,
        doctype=invoice_type,
        settings_name=settings_name,
        company=company,
        document_name=document_name,
    )


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
        route_key="SelectInvoice",  
        handler_function=on_success,
        request_method="POST",
        doctype=invoice_type,
        settings_name=settings_name,
        company=company or invoice.company,
        error_callback=on_error,
     
        document_name=document_name,
    )

@frappe.whitelist()
def verify_vsdc_invoice(
    id: str = None,
    document_name: str = None,
    invoice_type: str = "Sales Invoice",
    settings_name: str = None,
    company: str = None,
):
    """
    Verify and correct invoice details between ERPNext and
    ZRA Smart Invoice (Crystal VSDC) system.
    """
    invoice = frappe.get_doc(invoice_type, document_name)

    reference_number = invoice.name  # or use custom reference getter if needed

    _process_vsdc_invoice_request(
        id=id,
        document_name=document_name,
        invoice_type=invoice_type,
        settings_name=settings_name,
        company=company,
        handler_function=verify_and_fix_invoice_info,
        reference_number=reference_number,
    )