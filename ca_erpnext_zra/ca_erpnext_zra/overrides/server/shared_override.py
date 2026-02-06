from typing import Literal

import frappe
from frappe.model.document import Document

from ...apis.api_builder import EndpointsBuilder
from ...apis.api_processor import process_request
from ...doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME
from ...services.sales_service import (
	sales_information_submission_on_error,
	sales_information_submission_on_success,
)
from ...utils.payload_utils import (
	build_credit_note_payload,
	build_debit_note_payload,
	build_invoice_payload,
	build_rvat_sale_payload,
	get_invoice_reference_number,
)
from ...utils.settings_utils import get_settings
from ...utils.tax_utils import calculate_tax

endpoints_builder = EndpointsBuilder()


def before_save(doc: "Document", method: str | None = None) -> None:
	if not frappe.db.exists(SETTINGS_DOCTYPE_NAME, {"is_active": 1}):
		return
	calculate_tax(doc)


def _handle_sales_submission_success(response, document_name, doctype, settings_name, **kwargs):
	"""
	Globally defined function to act as the success callback wrapper for sales submissions.
	Replaces the non-picklable lambda function.
	"""

	try:
		sales_information_submission_on_success(
			response=response,
			document_name=document_name,
			doctype=doctype,
			settings_name=settings_name,
		)
	except Exception:
		frappe.log_error(
			title="sales_information_submission_on_success() failed", message=frappe.get_traceback()
		)


# --------------------------------------------------------------------------


def generic_invoices_on_submit_override(
	doc: Document, invoice_type: Literal["Sales Invoice", "POS Invoice"]
) -> None:
	"""
	Handles sending of Sales, Credit Notes, and now Debit Notes to VSDC.
	All API calls are asynchronous (via frappe.enqueue).
	"""

	company_name = doc.company
	settings_doc = get_settings(company_name)

	# Skip if prevented or already submitted
	if doc.custom_prevent_smart_submission or getattr(doc, "vsdc_invoice_number", None):
		return

	# =============== CREDIT NOTE SUBMISSION (Return) ==================
	if doc.is_return and doc.return_against:
		return_invoice = frappe.get_doc(invoice_type, doc.return_against)
		if not getattr(return_invoice, "custom_successfully_submitted", False):
			frappe.msgprint(
				f"Cannot submit credit note. The original invoice {doc.return_against} "
				f"was never successfully submitted to ZRA."
			)
			return

		reference_number = get_invoice_reference_number(return_invoice)
		payload = build_credit_note_payload(doc, settings_doc.name)

		frappe.enqueue(
			process_request,
			queue="default",
			is_async=True,
			request_data=payload,
			route_key="SaveCreditNote",
			handler_function=_handle_sales_submission_success,
			request_method="POST",
			document_name=doc.name,
			doctype=invoice_type,
			settings_name=settings_doc.name,
		)
		return

	# =============== DEBIT NOTE SUBMISSION ==================
	# Debit Note typically: doc.is_debit_note == 1 (custom field) OR doc.debit_note_against
	if hasattr(doc, "is_debit_note") and doc.is_debit_note:
		if not doc.return_against:
			frappe.throw("A Debit Note must reference an original Sales Invoice.")

		orig_invoice = frappe.get_doc("Sales Invoice", doc.return_against)

		if not getattr(orig_invoice, "custom_successfully_submitted", False):
			frappe.msgprint(
				f"Cannot submit Debit Note. Original invoice {doc.return_against} "
				f"was not successfully submitted to ZRA."
			)
			return

		payload = build_debit_note_payload(doc.name, settings_doc.name)

		frappe.enqueue(
			process_request,
			queue="default",
			is_async=True,
			request_data=payload,
			route_key="SaveDebitNote", 
			handler_function=_handle_sales_submission_success,
			request_method="POST",
			document_name=doc.name,
			doctype="Sales Invoice",
			settings_name=settings_doc.name,
			error_callback=sales_information_submission_on_error,
		)
		return

	# =============== NORMAL SALES INVOICE SUBMISSION ==================
	if getattr(doc, "custom_principal_id", None):
		payload = build_rvat_sale_payload(doc.name, settings_doc.name)
	else:
		payload = build_invoice_payload(doc, settings_doc.name)

	frappe.enqueue(
		process_request,
		queue="default",
		is_async=True,
		request_data=payload,
		route_key="SaveSales",
		handler_function=_handle_sales_submission_success,
		request_method="POST",
		document_name=doc.name,
		doctype=invoice_type,
		settings_name=settings_doc.name,
		company=company_name,
		error_callback=sales_information_submission_on_error,
	)


def submit_credit_note():
	pass
