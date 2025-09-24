
import frappe
from ..services.sales_service import (

    submit_credit_note
)

@frappe.whitelist()
def submit_credit_note(document_name: str, doctype: str, settings_name: str) -> None:
    """
    API endpoint to submit a Credit Note to Crystal VSDC.
    """
    submit_credit_note(document_name, doctype, settings_name)