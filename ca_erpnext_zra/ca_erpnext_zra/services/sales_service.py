import frappe
from frappe.model.document import Document

from ..apis.api_processor import process_request
from ..apis.invoice_processor import get_vsdc_invoice_details
from ..utils.payload_utils import (
	# build_stock_items_payload,
	# build_stock_master_payload,
	build_credit_note_payload,
)


def sales_information_submission_on_success(
	response: dict, document_name: str, doctype: str, settings_name: str, **kwargs
) -> None:
	"""
	Callback executed after a successful Sales Invoice submission
	to Crystal VSDC. Marks the document as submitted and triggers
	background fetch of invoice details from VSDC for reconciliation.
	"""

	#     invoice = frappe.get_doc(doctype, document_name)
	#     is_return = bool(getattr(invoice, "is_return", 0))

	#  # Build and send stock items payload
	#     stock_payload = build_stock_items_payload(invoice, settings_name, for_return=is_return)
	#     process_request(
	#         request_data=stock_payload,
	#         route_key="SaveStockItems",
	#         handler_function=None,
	#         request_method="POST",
	#         doctype="Sales Invoice",
	#         settings_name=settings_name,
	#         company=invoice.company
	#     )

	#     # Build and send stock master payload (sync quantities)
	#     item_codes = [i.item_code for i in invoice.items]
	#     master_payload = build_stock_master_payload(settings_name, item_codes)
	#     process_request(
	#         request_data=master_payload,
	#         route_key="SaveStockMaster",
	#         handler_function=None,
	#         request_method="POST",
	#         doctype="Sales Invoice",
	#         settings_name=settings_name,
	#         company=invoice.company
	#     )

	# Extract the actual data from the nested response structure
	result_data = response.get("Result", {})
	actual_data = result_data.get("data", {})
	# frappe.throw(str(actual_data))
	# Debug logging to verify the structure
	print(f"DEBUG - Full response: {response}")
	print(f"DEBUG - Result data: {result_data}")
	print(f"DEBUG - Actual data: {actual_data}")

	# Use the actual_data which contains the invoice information
	updates = {
		"custom_successfully_submitted": 1,
		"custom_scu_invoice_number": actual_data.get("cisInvcNo"),  # This should now work
		"custom_control_unit_date_time": actual_data.get(
			"vsdcRcptPbctDate"
		),  # Using vsdcRcptPbctDate instead of cfmDt
		"custom_total_receipt_number": actual_data.get("rcptNo"),
	}

	print(f"Sales submission success updates for {doctype} {document_name}: {updates}")

	frappe.db.set_value(doctype, document_name, updates)

	# Enqueue background fetch of invoice details for consistency check
	frappe.enqueue(
		get_vsdc_invoice_details,
		queue="long",
		document_name=document_name,
		invoice_type=doctype,
		settings_name=settings_name,
	)


def sales_information_submission_on_error(
	response: dict | str | None,
	url: str | None,
	doctype: str | None,
	document_name: str | None,
	payload: dict | None,
	settings_name: str | None,
):
	frappe.log_error(
		title="Sales Submission Failed",
		message=f"Failed sending invoice {document_name} of {doctype}\n"
		f"URL: {url}\n"
		f"Settings: {settings_name}\n"
		f"Payload: {payload}\n"
		f"Response: {response}",
	)


def submit_credit_note_service(
	response: dict,
	document_name: str,
	doctype: str,
	settings_name: str,
	**kwargs,
) -> None:
	"""
	Handles submission of Credit Notes (return invoices) to Crystal VSDC.

	Args:
	    response (dict): Response from the return-against invoice lookup.
	    document_name (str): The name of the Credit Note document in ERPNext.
	    doctype (str): ERPNext doctype (usually "Sales Invoice").
	    settings_name (str): Reference to Crystal VSDC settings doctype.
	"""
	doc: Document = frappe.get_doc(doctype, document_name)

	# Prepare payload for Crystal VSDC's Credit Note endpoint
	payload = build_credit_note_payload(doc, response)

	# Enqueue request to VSDC
	frappe.enqueue(
		process_request,
		queue="default",
		is_async=True,
		request_data=payload,
		route_key="CreditNoteSaveReq",  # Crystal VSDC endpoint
		handler_function=sales_information_submission_on_success,
		request_method="POST",
		doctype=doctype,
		settings_name=settings_name,
		company=doc.company,
	)
