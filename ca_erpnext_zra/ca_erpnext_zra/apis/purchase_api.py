import frappe
from frappe.model.document import Document
from ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils import get_active_smart_settings
from ..apis.api_processor import process_request
from ..utils.payload_utils import build_purchase_payload, build_debit_note_payload
from ..handlers.invoice_handler import purchase_invoice_submission_on_success
from ..handlers.purchase_handlers import purchase_search_on_success
from ..doctype.doctype_names_mapping import REGISTERED_PURCHASES_DOCTYPE_NAME
from datetime import datetime

def submit_smart_purchase_invoice(doc: Document) -> None:
    """
    Submit a Purchase Invoice or Debit Note to the Smart Invoice System (ZRA).
    Handles multi-company setups and prevents duplicate submissions.
    """

     # Ensure we have a proper Document object
    if isinstance(doc, str):
        frappe.throw(str(doc))
        doc = frappe.get_doc("Purchase Invoice", doc)
    
    # Skip if already submitted to Smart
    if getattr(doc, "custom_smart_invoice_number", None):
        frappe.log_error(f"Invoice {doc.name} already has a Smart Invoice Number — skipping submission.")
        return

    company_name = doc.company
    active_settings = get_active_smart_settings()

    # Find settings for this company
    company_setting = next((s for s in active_settings if s.get("company") == company_name), None)

    if not company_setting:
        frappe.log_error(f"No Smart settings found for company: {company_name}", "Smart Submission Error")
        return

    # Skip if Smart submission is explicitly disabled
    if getattr(doc, "prevent_smart_submission", False):
        frappe.msgprint("Smart submission prevented for this document.")
        return

    try:
        # Determine submission type
        if doc.is_return:
            route_key = "saveDebitNote"
            payload = build_debit_note_payload(doc.name, company_setting.get("name"))
            success_message = "Smart Debit Note submission queued successfully."
        else:
            route_key = "savePurchase"
            payload = build_purchase_payload(doc.name, company_setting.get("name"))
            success_message = "Smart Purchase Invoice submission queued successfully."

        # Process API request
        process_request(
            request_data=payload,
            route_key=route_key,
            handler_function=lambda response, **_: purchase_invoice_submission_on_success(
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

        frappe.msgprint(success_message)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Smart Purchase/Debit Note Submission Failed")
        frappe.throw(f"Error submitting to Smart: {e}")


def on_error(error):
    """Generic error logger for Smart API failures."""
    frappe.log_error(
        title="VSDC API Error",
        message=f"Failed to submit document to VSDC: {error}",
    )


@frappe.whitelist()
def send_purchase_details(doc, method=None) -> None:
    """
    Manually trigger Smart submission for a Purchase Invoice or Debit Note.
    """
    submit_smart_purchase_invoice(doc)
import frappe
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password
from ..utils.settings_utils import get_settings



@frappe.whitelist()
def perform_purchases_search(company: str) -> None:
    """
    Fetch purchases from ZRA Smart Invoice System for a given company.
    """
    # Get active Smart settings for the company
    settings = get_settings(company)
    if not settings:
        frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings found for {company}")
        return

    # Decrypt TPIN from Smart settings
    tpin = get_decrypted_password(
        "Crystal ZRA Smart Invoice Settings",
        settings.name,
        "tpin",
        raise_exception=False,
    ) or ""

    # Default branch ID
    bhf_id = settings.get("bhfid") or "000"
    last_req_dt = datetime.now().strftime("%Y%m%d%H%M%S")
    # Prepare request payload (required by ZRA API)
    request_data = {
        "Tpin": tpin,
        "BhfId": bhf_id,
        "LastReqDt": "20231215000000", 
    }

    try:
        process_request(
            request_data=request_data,
            route_key="selectTrnsPurchaseSales",
            handler_function=purchase_search_on_success,
            request_method="POST",  # ZRA requires POST for this endpoint
            doctype=REGISTERED_PURCHASES_DOCTYPE_NAME,
        )

        frappe.msgprint("Smart purchase fetch request sent successfully.")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Smart Purchase Fetch Failed")
        frappe.throw(f"Error fetching purchases from ZRA: {e}")
