from .qr_utils import generate_and_attach_qr_code
from frappe.utils import get_datetime



def map_vsdc_fields(data: dict, docname: str, doctype: str) -> dict:
    """
    Map Crystal VSDC (ZRA Smart Invoice) response data
    to ERPNext custom fields.
    """
    if not data:
        return {}

    qr_url =  data.get("qrCodeUrl")
    
    image_url = generate_and_attach_qr_code(qr_url, docname, doctype) if qr_url else None

    return {
        "custom_scu_invoice_number": data.get("cisInvcNo"),
        "custom_current_receipt_number": data.get("rcptNo"),
        "custom_internal_data": data.get("intrlData"),
        "custom_receipt_signature": data.get("rcptSign"),
        "custom_receipt_date": data.get("vsdcRcptPbctDate"),
        "custom_scu_id": data.get("sdcId"),
        "custom_scu_mrc_no": data.get("mrcNo"),
        "custom_qr_code_url": data.get("qrCodeUrl"),
         "custom_qr_code": image_url,
       
    }
