import frappe
from frappe.model.document import Document

from .shared_override import generic_invoices_on_submit_override
from ...utils.settings_utils import  get_settings
from ...utils.tax_utils import calculate_tax


def on_submit(doc: Document, method: str = None) -> None:
    """Triggered when a Sales Invoice is submitted in ERPNext.
    Pushes invoice or return details to Crystal VSDC if auto-submission is enabled.
    """
    # frappe.log_error(" ENTERED on_submit for Sales Invoice: " + doc.name, "DEBUG: Sales Invoice Hook")

    settings_doc = get_settings()
    if not settings_doc or not settings_doc.sales_auto_submission_enabled:
        frappe.log_error("Auto submission disabled or no settings found", "DEBUG: Sales Invoice Hook")
        return

    # frappe.throw(str(doc))
    # Always compute tax
    calculate_tax(doc)

    #  Skip only if explicitly prevented
    if doc.custom_prevent_smart_submission:
        return

    #  Handle NORMAL invoice submission
    if not doc.is_return and doc.is_opening == "No":
        if doc.custom_successfully_submitted:
            # Already submitted previously, skip
            return
        try:
            generic_invoices_on_submit_override(doc, "Sales Invoice")
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Crystal VSDC Sales Submission Failed for {doc.name}")
            frappe.throw(f"Failed to auto-submit invoice to Crystal VSDC: {e}")
        return

    #  Handle RETURN (Credit Note)
    if doc.is_return:
        try:
            if not doc.return_against:
                frappe.throw("Return invoice is missing the 'Return Against' reference.")

            return_invoice = frappe.get_doc("Sales Invoice", doc.return_against)

            # Only allow returns for invoices that were successfully submitted to ZRA
            if not getattr(return_invoice, "custom_successfully_submitted", False):
                frappe.msgprint(
                    f"Return against invoice {doc.return_against} was not successfully submitted. Cannot process return."
                )
                return

            # Proceed with return submission
            generic_invoices_on_submit_override(doc, "Sales Invoice")

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Crystal VSDC Return Submission Failed for {doc.name}")
            frappe.throw(f"Failed to auto-submit credit note to Crystal VSDC: {e}")

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
