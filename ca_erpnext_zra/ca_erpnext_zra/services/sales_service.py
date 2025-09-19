import frappe
from ..apis.api_processor import process_request
from ..utils.payload_utils import build_return_invoice_payload
from ..services.sales_service import sales_information_submission_on_success


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
    error: dict | Exception,
    document_name: str,
    doctype: str,
    settings_name: str,
    **kwargs,
) -> None:
    """
    Error callback for failed Sales Invoice submission to Crystal VSDC.

    Logs error details, marks submission as failed,
    and optionally notifies the user.
    """

    # Convert error into readable string
    error_message = str(error) if isinstance(error, Exception) else frappe.as_json(error)

    # Update the document to reflect submission failure
    frappe.db.set_value(
        doctype,
        document_name,
        {
            "custom_successfully_submitted": 0,
            "custom_submission_error": error_message[:1000],  # store truncated error
        },
    )

    # Log for server-side debugging
    frappe.log_error(
        title=f"{doctype} Submission Error - {document_name}",
        message=error_message,
    )

    # Optional user notification
    frappe.msgprint(
        f"Failed to submit {doctype} <b>{document_name}</b> to Crystal VSDC.<br><br>"
        f"<b>Error:</b> {frappe.utils.escape_html(error_message)}"
    )
import frappe
from frappe.model.document import Document





def submit_credit_note(
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
