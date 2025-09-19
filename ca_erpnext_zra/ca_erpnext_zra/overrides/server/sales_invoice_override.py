import frappe
from frappe.model.document import Document

from ...services.sales_service import generic_invoices_on_submit_override
from ...utils.settings_utils import  get_settings
from ...utils.tax_utils import calculate_tax

def on_submit(doc: Document, method: str = None) -> None:
    """Triggered when a Sales Invoice is submitted in ERPNext.
    Pushes the invoice details to Crystal VSDC if auto-submission is enabled.
    """
    company_name = doc.company
    settings_doc = get_settings(company_name=company_name)

    if not settings_doc:
        return

    # Compute tax breakdown before sending
    calculate_tax(doc)

    # Only push to VSDC if certain conditions are met
    if (
        doc.custom_successfully_submitted == 0
        and doc.prevent_vsdc_submission == 0
        and doc.is_opening == "No"
        and settings_doc.sales_auto_submission_enabled
    ):
        try:
            generic_invoices_on_submit_override(doc, "Sales Invoice")
        except frappe.ValidationError as e:
            frappe.log_error(
                "Crystal VSDC Submission Error",
                f"Error submitting Sales Invoice {doc.name} to Crystal VSDC: {str(e)}",
            )


def before_cancel(doc: Document, method: str = None) -> None:
    """Prevent cancellation of invoices already submitted to Crystal VSDC."""

    if doc.doctype == "Sales Invoice" and doc.custom_successfully_submitted:
        frappe.throw(
            "This Sales Invoice has already been <b>submitted</b> to Crystal VSDC and cannot be <span style='color:red'>Canceled.</span><br>"
            "If you need to make adjustments, please issue a Credit Note."
        )
    elif doc.doctype == "Purchase Invoice" and doc.custom_successfully_submitted:
        frappe.throw(
            "This Purchase Invoice has already been <b>submitted</b> to Crystal VSDC and cannot be <span style='color:red'>Canceled.</span><br>"
            "If you need to make adjustments, please issue a Debit Note."
        )


@frappe.whitelist()
def send_invoice_details(name: str) -> None:
    """Manual trigger to push a Sales Invoice to Crystal VSDC."""
    doc = frappe.get_doc("Sales Invoice", name)

    # Skip opening entries
    if doc.is_opening == "Yes":
        return

    generic_invoices_on_submit_override(doc, "Sales Invoice")
