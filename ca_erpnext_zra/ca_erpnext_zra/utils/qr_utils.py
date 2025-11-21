from io import BytesIO

import frappe
import qrcode
from frappe.core.doctype.file.file import create_new_folder
from frappe.utils import now


def generate_and_attach_qr_code(url: str, docname: str, doctype: str) -> str:
	"""
	Generate a QR code image from a ZRA Smart Invoice QR URL
	and attach it to the specified ERPNext document.
	Returns the file URL.
	"""
	if not url:
		return None

	# Generate QR code image
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

	# Ensure folder exists (optional)
	create_new_folder("Smart_QR", "Home")

	# Save file using frappe's file API
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"Smart-QR-{docname}-{now()}.png",
			"is_private": 0,
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"content": buffer.getvalue(),
			"folder": "Home/Smart_QR",
		}
	)
	file_doc.save(ignore_permissions=True)

	return file_doc.file_url
