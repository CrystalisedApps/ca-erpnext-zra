import qrcode
from io import BytesIO
import frappe
from frappe.utils import now


def generate_and_attach_qr_code(url: str, docname: str, doctype: str) -> str:
    """
    Generate a QR code image from a ZRA Smart Invoice QR URL
    and attach it to the specified ERPNext document.
    """
    if not url:
        return None

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"ZRA-QR-{docname}-{now()}.png",
        "is_private": 0,
        "attached_to_doctype": doctype,
        "attached_to_name": docname,
    })
    file_doc.save(ignore_permissions=True)

    file_doc.db_set("content", buffer.getvalue())
    return file_doc.file_url
