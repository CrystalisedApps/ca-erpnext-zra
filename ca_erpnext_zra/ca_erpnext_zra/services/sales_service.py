import frappe
from ..apis.api_processor import process_request
from ..utils.payload_utils import build_return_invoice_payload



def sales_information_submission_on_success(
    response: dict,
    document_name: str,
    doctype: str,
    settings_name: str,
    **kwargs
) -> None:
    """
    Callback executed after a successful Sales Invoice submission
    to Crystal VSDC. Marks the document as submitted and triggers
    background fetch of invoice details from VSDC for reconciliation.
    """
    updates = {
        "custom_successfully_submitted": 1,
        "vsdc_invoice_number": response.get("cisInvcNo"),  # Crystal VSDC returns this unique invoice number
        "vsdc_confirmation_date": response.get("cfmDt"),   # Confirmation date if available
    }

    frappe.db.set_value(doctype, document_name, updates)

    # Enqueue background fetch of invoice details for consistency check
    frappe.enqueue(
        "ca_erpnext_zra.ca_erpnext_zra.services.sales_service.get_invoice_details",
        document_name=document_name,
        invoice_type=doctype,
        settings_name=settings_name,
        queue="long",
    )


def sales_information_submission_on_error(
    response: dict | str | None,
    url: str | None,
    doctype: str | None,
    document_name: str | None,
    payload: dict | None,
    settings_name: str | None,
):
    frappe.log_error(
        title="Sales Submission Failed",
        message=f"Failed sending invoice {document_name} of {doctype}\n"
                f"URL: {url}\n"
                f"Settings: {settings_name}\n"
                f"Payload: {payload}\n"
                f"Response: {response}"
    )

import frappe
from frappe.model.document import Document





def submit_credit_note_service(
    response: dict,
    document_name: str,
    doctype: str,
    settings_name: str,
    **kwargs,
) -> None:
    """
    Handles submission of Credit Notes (return invoices) to Crystal VSDC.

    Args:
        response (dict): Response from the return-against invoice lookup.
        document_name (str): The name of the Credit Note document in ERPNext.
        doctype (str): ERPNext doctype (usually "Sales Invoice").
        settings_name (str): Reference to Crystal VSDC settings doctype.
    """
    doc: Document = frappe.get_doc(doctype, document_name)

    # Prepare payload for Crystal VSDC's Credit Note endpoint
    payload = build_return_invoice_payload(doc, response)

    # Enqueue request to VSDC
    frappe.enqueue(
        process_request,
        queue="default",
        is_async=True,
        request_data=payload,
        route_key="CreditNoteSaveReq",  # Crystal VSDC endpoint
        handler_function=sales_information_submission_on_success,
        request_method="POST",
        doctype=doctype,
        settings_name=settings_name,
        company=doc.company,
    )
