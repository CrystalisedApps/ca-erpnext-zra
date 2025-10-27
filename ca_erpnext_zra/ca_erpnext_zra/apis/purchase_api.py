import frappe
from frappe.model.document import Document
from ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils import (
    get_active_smart_settings,
   
   
)
from ..apis.api_processor import process_request
from ..utils.payload_utils import build_purchase_payload
from ..handlers.invoice_handler import purchase_invoice_submission_on_success


def submit_smart_purchase_invoice(doc: Document) -> None:
    """
    Submit a Purchase Invoice to the Smart Invoice System (ZRA).
    Handles multi-company setups and prevents duplicate submissions.
    """

    # Skip if it's a return or already submitted to Smart
    if doc.is_return or getattr(doc, "custom_smart_invoice_number", None):
        return

    company_name = doc.company
    active_settings = get_active_smart_settings()

    # Find settings for this company
    company_setting = next(
        (s for s in active_settings if s.get("company") == company_name), None
    )

    if not company_setting:
        frappe.log_error(f"No Smart settings found for company: {company_name}", "Smart Submission Error")
        return

    # Skip if Smart submission is explicitly disabled
    if getattr(doc, "prevent_smart_submission", False):
        frappe.msgprint("Smart submission prevented for this document.")
        return

    try:
        payload = build_purchase_payload(doc.name,company_setting.get("name"))
        process_request(
            payload,
             "savePurchase",
            lambda response, **_: purchase_invoice_submission_on_success(
            response=response,
            document_name=doc.name,
            doctype="Purchase Invoice",
            settings_name=company_setting["name"],
        ),
        request_method="POST",
            doctype="Purchase Invoice",
            document_name=doc.name,
            settings_name=company_setting["name"],
        )
        frappe.msgprint("Smart Purchase Invoice submission queued successfully.")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Smart Purchase Invoice Submission Failed")
        frappe.throw(f"Error submitting to Smart: {e}")

def on_error(error):
        frappe.log_error(
            title="VSDC API Error",
            message=f"Failed to fetch VSDC invoice details: {error}"
        )
def smart_purchase_on_success(response, docname: str):
    """
    Called when Smart Purchase Invoice submission is successful.
    """
    try:
        doc = frappe.get_doc("Purchase Invoice", docname)
        doc.db_set("custom_smart_invoice_number", response.get("cisInvcNo"))
        doc.db_set("custom_smart_submission_status", "Submitted")
        frappe.msgprint(f"Smart Invoice submitted successfully — Smart No: {response.get('cisInvcNo')}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Smart Purchase On Success Handler Failed")


@frappe.whitelist()
def send_purchase_details(doc,method=None) -> None:
    """
    Manually trigger Smart submission for a Purchase Invoice.
    """
   
    submit_smart_purchase_invoice(doc)
