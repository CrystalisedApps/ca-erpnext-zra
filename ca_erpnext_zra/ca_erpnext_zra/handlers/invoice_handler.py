import frappe
from ..utils.mapping_utils import map_vsdc_fields
from ..utils.qr_utils import generate_and_attach_qr_code




def update_invoice_info(
    response: dict,
    document_name: str,
    doctype: str = "Sales Invoice",
    settings_name: str | None = None,
    **kwargs,
) -> None:
    """
    Updates a Sales Invoice or Credit Note document with details from
    the Crystal VSDC (ZRA Smart Invoice) response.
    """
    try:
        process_invoice_response(response, document_name, doctype)
        frappe.msgprint(f"ZRA Smart Invoice data synced for {document_name}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Crystal VSDC Update Failed")
        frappe.throw("Failed to update document from ZRA response.")


def process_invoice_response(response: dict, document_name: str, doctype: str) -> None:
    """
    Common handler to process ZRA Smart Invoice response
    and update ERPNext document fields.
    """
    try:
        if not response:
            frappe.throw("Empty response received from ZRA Smart Invoice API.")

        # Expected successful structure from ZRA Smart Invoice
        # e.g. {
        #   "Version": "1.0",
        #   "StatusCode": 200,
        #   "IsSuccess": True,
        #   "Result": {
        #       "invoiceNo": "ACC-SINV-2025-00012",
        #       "zraInvoiceNo": "INV000123456",
        #       "qrCodeUrl": "https://vsdc.zra.org.zm/qrcode/INV000123456",
        #       "signingTime": "2025-10-06T09:23:15",
        #   }
        # }

        result = response.get("Result")
        data = result.get("data")
        


        if not result:
            frappe.throw(f"Unexpected response format: {frappe.as_json(response)}")

        updates = {
            **map_vsdc_fields(data, document_name, doctype),
    }
        # Optional: capture error fields if failed
        # if not response.get("IsSuccess"):
        #     updates.update({
        #         "custom_submission_status": "Failed",
        #         "custom_zra_error": response.get("ErrorMessage"),
        #     })

        frappe.db.set_value(doctype, document_name, updates)
        frappe.db.commit()
        frappe.publish_realtime("refresh_form", document_name)
    except Exception as e:
            frappe.log_error(f"Invoice Update", str(e))
            frappe.throw(f"Failed to auto-submit credit note to Crystal VSDC: {e}")
        

