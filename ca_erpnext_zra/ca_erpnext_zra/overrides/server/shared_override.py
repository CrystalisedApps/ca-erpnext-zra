from typing import Literal

import frappe
from frappe.model.document import Document

from ...apis.api_processor import process_request
from ...apis.api_builder import EndpointsBuilder
from ...services.sales_service import (
    sales_information_submission_on_success,
     sales_information_submission_on_error,
)
from ...utils.settings_utils import get_settings
from ...utils.payload_utils import get_invoice_reference_number
from ...utils.payload_utils import build_invoice_payload, build_credit_note_payload
from ...utils.tax_utils import calculate_tax
from ...doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME

endpoints_builder = EndpointsBuilder()
def before_save(doc: "Document", method: str | None = None) -> None:
    if not frappe.db.exists(SETTINGS_DOCTYPE_NAME, {"is_active": 1}):
        return
    calculate_tax(doc)
def _handle_sales_submission_success(response, document_name, doctype, settings_name, **kwargs):
    """
    Globally defined function to act as the success callback wrapper for sales submissions.
    Replaces the non-picklable lambda function.
    """
    
    try:
        sales_information_submission_on_success(
            response=response,
            document_name=document_name,
            doctype=doctype,
            settings_name=settings_name,
        )
    except Exception:
        frappe.log_error(
            title="sales_information_submission_on_success() failed",
            message=frappe.get_traceback()
        )
# --------------------------------------------------------------------------

def generic_invoices_on_submit_override(
    doc: Document, invoice_type: Literal["Sales Invoice", "POS Invoice"]
) -> None:
    """
    Handles sending of Sales information from relevant invoice documents
    to Crystal VSDC. The logic is now asynchronous for all API calls via frappe.enqueue.
    """
    # frappe.throw(str(doc))
    company_name = doc.company
    settings_doc = get_settings() # Assuming this is correctly imported and available

    # Skip submission if flagged or already submitted
    if (
        doc.custom_prevent_smart_submission
        or getattr(doc, "vsdc_invoice_number", None)
        or doc.status == "Credit Note Issued"
    ):
        return

    # Handle Credit Notes (returns)
    if doc.is_return:
        return_invoice = frappe.get_doc(invoice_type, doc.return_against)
        if not getattr(return_invoice, "custom_successfully_submitted", False):
            frappe.msgprint(
                f"Return against invoice {doc.return_against} was not successfully submitted. Cannot process return."
            )
            return

        from ...apis.sales_api import submit_credit_note

        reference_number = get_invoice_reference_number(return_invoice)
        request_data = {
            "document_name": doc.name,
            "company": company_name,
            "reference_number": reference_number,
        }
        payload = build_credit_note_payload(doc, settings_doc.name)
        # Compute tax breakdown before sending (assuming calculate_tax is defined)
        calculate_tax(doc) 

        # Enqueue the Credit Note submission
        frappe.enqueue(
            process_request,
            queue="default",
            is_async=True,
            request_data=payload,
            route_key="SaveCreditNote",  # Crystal-specific endpoint
            handler_function=submit_credit_note,
            request_method="POST",
            doctype=invoice_type,
            settings_name=settings_doc.name,
        )

    else:
        payload = build_invoice_payload(doc, settings_doc.name)
       
        frappe.enqueue(
            process_request,
            queue="default",
            is_async=True,
            
            request_data=payload,
            route_key="SaveSales",  
            
            handler_function = _handle_sales_submission_success,
            request_method="POST",
            document_name=doc.name, # This is the context data needed by the callback
            doctype=invoice_type,   # This is the context data needed by the callback
            settings_name=settings_doc.name, # This is the context data needed by the callback
            company=company_name,
            error_callback=sales_information_submission_on_error,
        )





def submit_credit_note():
    pass