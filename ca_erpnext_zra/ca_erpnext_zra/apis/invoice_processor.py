import frappe
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password

from ca_erpnext_zra.ca_erpnext_zra.apis.api_processor import process_request
from ..utils.settings_utils import get_settings
from ..utils.payload_utils import (  # keep payload logic modular
	build_credit_note_payload,
	build_debit_note_payload,
	build_invoice_payload,
)
from ..handlers.invoice_handler import update_invoice_info

@frappe.whitelist()
def _process_vsdc_invoice_request(
	id: str = None,
	document_name: str = None,
	invoice_type: str = "Sales Invoice",
	settings_name: str = None,
	company: str = None,
	handler_function=None,
	reference_number: str = None,
	is_return: bool = False,
	is_debit_note: bool = False,
	original_invoice_id: str = None,
):
	"""
	Unified helper for Crystal VSDC (ZRA Smart Invoice) requests.
	Handles:
	  - Normal Sales Invoice submission
	  - Credit Notes (return)
	  - Debit Notes (undercharge / omitted items / wrong amount)
	  - Invoice lookup
	"""

	invoice = frappe.get_doc(invoice_type, document_name)

	# ----------------------------------------------------
	# Fetch active settings
	# ----------------------------------------------------
	if not settings_name:
		settings = frappe.get_all(
			"Crystal ZRA Smart Invoice Settings",
			filters={"is_active": 1},
			fields=["name"],
			limit=1,
		)
		if not settings:
			frappe.throw("No active Crystal ZRA Smart Invoice Settings found.")
		settings_name = settings[0]["name"]

	# Base request data
	request_data = {
		"document_name": document_name,
		"company": company or invoice.company,
	}

	# ----------------------------------------------------
	# Determine which route we should call
	# Priority:
	#   1. Debit Note
	#   2. Credit Note
	#   3. Sales
	#   4. Lookup / SelectInvoice
	# ----------------------------------------------------

	route_key = "SelectInvoice"

	# Debit Note (High Priority)
	if is_debit_note or getattr(invoice, "is_debit_note", False):
		route_key = "SaveDebitNote"

	# Credit Note (Return)
	elif is_return or invoice.is_return:
		route_key = "SaveCreditNote"

	# Normal Sales submission
	elif not id:
		route_key = "SaveSales"

	#  Lookup by ID
	elif id:
		route_key = "SelectInvoice"

	# ----------------------------------------------------
	# Attach Invoice Reference for Credit/Debit Notes
	# ----------------------------------------------------

	if route_key in ["SaveCreditNote", "SaveDebitNote"]:
		# Link to original invoice SLIP/Smart ID
		original_smart_id = None

		if original_invoice_id:
			# manual DN/CN request
			original_smart_id = original_invoice_id
		elif invoice.return_against:
			# ERPNext return document
			original_smart_id = frappe.db.get_value(
				"Sales Invoice", invoice.return_against, "original_invoice_number"
			)
		else:
			# fallback — cannot submit CN/DN without original link
			frappe.throw("Original Invoice reference is required for Credit/Debit Notes.")

		request_data["invoice"] = original_smart_id

	# ----------------------------------------------------
	# Attach Correct Payload
	# ----------------------------------------------------

	if route_key == "SaveSales":
		payload = build_invoice_payload(invoice, settings_name)
		request_data.update(payload)

	elif route_key == "SaveCreditNote":
		payload = build_credit_note_payload(invoice, settings_name)
		request_data.update(payload)

	elif route_key == "SaveDebitNote":
		payload = build_debit_note_payload(invoice, settings_name)
		request_data.update(payload)

	# ----------------------------------------------------
	# Execute Smart Invoice API Request
	# ----------------------------------------------------

	return process_request(
		request_data=request_data,
		route_key=route_key,
		handler_function=handler_function,
		doctype=invoice_type,
		settings_name=settings_name,
		company=company,
		document_name=document_name,
	)


@frappe.whitelist()
def get_vsdc_invoice_details(
	document_name: str,
	invoice_type: str = "Sales Invoice",
	settings_name: str = None,
	company: str = None,
	**kwargs,
):
	"""
	Fetch and refresh Crystal VSDC (ZRA Smart Invoice) details for a Sales Invoice,
	using the centralized `process_request` API wrapper.
	"""
	# ---  Debug Logging: confirm arguments ---
	frappe.log_error(
		title="VSDC Invoice Details Debug",
		message=f"""
         get_vsdc_invoice_details() called with:
        - document_name: {document_name}
        - invoice_type: {invoice_type}
        - settings_name: {settings_name}
        - company: {company}
        - kwargs: {kwargs}
        """,
	)

	# --- Optional: handle 'kwargs' wrapping (if job was enqueued as string path) ---
	if not document_name and "kwargs" in kwargs:
		inner = kwargs.get("kwargs") or {}
		document_name = inner.get("document_name")
		invoice_type = inner.get("invoice_type", invoice_type)
		settings_name = inner.get("settings_name", settings_name)
		company = inner.get("company", company)

		frappe.log_error(
			title="VSDC Invoice Details (Recovered from kwargs)",
			message=f"Recovered args from kwargs → document_name={document_name}, invoice_type={invoice_type}, settings_name={settings_name}",
		)

	# --- Sanity check ---
	if not document_name:
		frappe.throw(" Missing document_name in get_vsdc_invoice_details()")

	# Fetch invoice
	invoice = frappe.get_doc(invoice_type, document_name)

	# Fetch first active settings record
	settings = get_settings(settings_name)

	if not settings:
		frappe.throw("No active Crystal ZRA Smart Invoice Settings found.")

	
	# Decrypt TPIN

	tpin = settings.get("tpin")

	# Build payload
	payload = {
		"tpin": tpin,
		"bhfId": "000",
		"CisInvcNo": invoice.name,
	}

	# Define success handler for response
	def on_success(response, **_):
		if not response:
			frappe.throw("Empty response from ZRA Smart Invoice system.")
		if not response.get("IsSuccess"):
			frappe.throw(f"ZRA Error: {response.get('ErrorMessage', 'Unknown error')}")

		update_invoice_info(
			response=response,
			document_name=invoice.name,
			doctype=invoice.doctype,
		)

		frappe.msgprint(f"Invoice details synced successfully with ZRA for {invoice.name}")

	# Define error handler
	def on_error(response=None, **kwargs):
		frappe.log_error(title="VSDC API Error", message=f"Failed to fetch VSDC invoice details: {response}")

	# Use process_request to send the request
	process_request(
		request_data=payload,
		route_key="SelectInvoice",
		handler_function=on_success,
		request_method="POST",
		doctype=invoice_type,
		settings_name=settings_name,
		company=company or invoice.company,
		error_callback=on_error,
		document_name=document_name,
	)


# @frappe.whitelist()
# def verify_vsdc_invoice(
# 	id: str = None,
# 	document_name: str = None,
# 	invoice_type: str = "Sales Invoice",
# 	settings_name: str = None,
# 	company: str = None,
# ):
# 	"""
# 	Verify and correct invoice details between ERPNext and
# 	ZRA Smart Invoice (Crystal VSDC) system.
# 	"""
# 	invoice = frappe.get_doc(invoice_type, document_name)

# 	reference_number = invoice.name  # or use custom reference getter if needed

# 	_process_vsdc_invoice_request(
# 		id=id,
# 		document_name=document_name,
# 		invoice_type=invoice_type,
# 		settings_name=settings_name,
# 		company=company,
# 		handler_function=verify_and_fix_invoice_info,
# 		reference_number=reference_number,
# 	)
