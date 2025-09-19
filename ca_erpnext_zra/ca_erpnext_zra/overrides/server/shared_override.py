from typing import Literal

import frappe
from frappe.model.document import Document

from ...apis.api_processor import process_request
from ...apis.api_builder import EndpointsBuilder
# from services.remote_response_status_handlers import (
#     sales_information_submission_on_success,
#     sales_information_submission_on_error,
# )
from ...utils.settings_utils import get_settings
from ...utils.payload_utils import build_invoice_payload, get_invoice_reference_number

endpoints_builder = EndpointsBuilder()


def generic_invoices_on_submit_override(
    doc: Document, invoice_type: Literal["Sales Invoice", "POS Invoice"]
) -> None:
    """
    Handles sending of Sales information from relevant invoice documents
    to Crystal VSDC.
    """

    company_name = doc.company
    settings_doc = get_settings(company_name=company_name)

    # Skip submission if flagged or already submitted
    if (
        doc.prevent_vsdc_submission
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

        # from ...services.sales_service import submit_credit_note

        reference_number = get_invoice_reference_number(return_invoice)
        request_data = {
            "document_name": doc.name,
            "company": company_name,
            "reference_number": reference_number,
        }

        frappe.enqueue(
            process_request,
            queue="default",
            is_async=True,
            request_data=request_data,
            route_key="CreditNoteSaveReq",  # Crystal-specific endpoint
            handler_function=submit_credit_note,
            doctype=invoice_type,
            settings_name=settings_doc.name,
        )

    else:
        # Build the payload for Crystal VSDC SalesInvoiceSave endpoint
        payload = build_invoice_payload(doc, settings_doc.name)
        additional_context = {
            "invoice_type": invoice_type,
        }

        process_request(
            payload,
            "SalesInvoiceSaveReq",  # Crystal VSDC endpoint
            lambda response, **kwargs: sales_information_submission_on_success(
                response=response,
                **additional_context,
                **kwargs,
            ),
            request_method="POST",
            doctype=invoice_type,
            settings_name=settings_doc.name,
            company=company_name,
            error_callback=sales_information_submission_on_error,
        )

def sales_information_submission_on_success():
    pass

def sales_information_submission_on_error():
    pass

def submit_credit_note():
    pass