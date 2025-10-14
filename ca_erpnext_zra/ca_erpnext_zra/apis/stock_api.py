

import frappe
from ..utils.payload_utils import build_sales_payload
from .api_processor import process_request
from ..utils.settings_utils import get_settings
from frappe.utils.password import get_decrypted_password

@frappe.whitelist()
def send_sales_to_zra(doc, method):
    try:
        company_name = doc.company
        
        settings = get_settings()
        tpin = get_decrypted_password(
            "Crystal ZRA Smart Invoice Settings",
            settings.name,      
            "tpin",               # fieldname
            raise_exception=False
        ) or ""
        if not settings:
            frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings for {company_name}")
            return

        payload = build_sales_payload(doc.name, company_tpin=tpin, user=frappe.session.user)

        process_request(
            request_data=payload,
            route_key="saveStockItems", 
            request_method="POST",
            doctype="Sales Invoice",
            document_name=doc.name,
        )

        frappe.logger().info(f"✅ Successfully queued sales submission for {doc.name}")

    except Exception as e:
        frappe.log_error(title="ZRA Sales Submission Error", message=str(e))
