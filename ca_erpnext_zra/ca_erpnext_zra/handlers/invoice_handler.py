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


def purchase_invoice_submission_on_success(
	response: dict, doctype: str, document_name: str, **kwargs
) -> None:
	updates = {"custom_submitted_successfully": 1}

	frappe.db.set_value(doctype, document_name, updates)

	frappe.db.commit()  # Ensure the change is saved immediately
	frappe.logger().info(f"Marked {document_name} as successfully submitted to Smart Invoice.")


# def verify_and_fix_invoice_info(
# 	response: dict, document_name: str, doctype: str, settings_name: str | None = None, **kwargs
# ) -> None:
# 	"""
# 	Verify and reconcile invoice info with ZRA Smart Invoice data.
# 	Automatically handles revisions, mismatches, and resends if required.
# 	"""
# 	doc = frappe.get_doc(doctype, document_name)
# 	data = response.get("Data") if response else None

# 	revision_count = int(doc.get("revision_count") or 0)
# 	if revision_count > 0:
# 		verify_and_fix_invoice_revisions(doctype, document_name, data, settings_name)

# 	# If no response data, try resending the invoice
# 	if not data:
# 		resend_invoice(document_name, doctype)
# 		return

# 	# If invoice lacks SCU data, re-sign and re-send
# 	if not data.get("scu_data") and doc.get("custom_vsdc_number"):
# 		frappe.logger("zra_sync").info(f"Re-signing invoice {document_name}")
# 		process_sales_sign(document_name, doctype, doc.custom_vsdc_number)
# 		return

# 	# Build payload for comparison
# 	invoice_data = (
# 		build_return_invoice_payload(doc, data)
# 		if doc.is_return
# 		else build_invoice_payload(doc, settings_name)
# 	)

# 	# Compare local vs ZRA data
# 	if is_invoice_data_matching(invoice_data, data):
# 		process_invoice_response(response, document_name, doctype)
# 	else:
# 		handle_invoice_mismatch(doc, document_name, doctype, settings_name, data)


# def verify_and_fix_invoice_revisions(
# 	doctype: str, document_name: str, data: dict, settings_name: str | None = None
# ) -> None:
# 	"""Verify and enqueue fixing of previous invoice revisions if necessary"""
# 	doc = frappe.get_doc(doctype, document_name)
# 	revision_count = int(doc.get("revision_count") or 0)

# 	if revision_count <= 0:
# 		return

# 	revisions_to_check = [f"{document_name}-REV{i}" for i in range(1, revision_count + 1)]

# 	for rev_docname in revisions_to_check:
# 		frappe.enqueue(
# 			check_and_credit_invoice_revision,
# 			queue="short",
# 			doctype=doctype,
# 			document_name=document_name,
# 			reference_number=rev_docname,
# 			settings_name=settings_name,
# 		)


# def check_and_credit_invoice_revision(
# 	doctype: str,
# 	document_name: str,
# 	reference_number: str,
# 	settings_name: str | None = None,
# ) -> None:
# 	"""
# 	Checks a previous invoice revision against ZRA and, if necessary,
# 	issues a credit note to reverse the outdated record.
# 	"""
# 	doc = frappe.get_doc(doctype, document_name)

# 	frappe.logger("zra_sync").info(f"Checking invoice revision for {document_name} (Ref: {reference_number})")

# 	if not doc.get("custom_vsdc_number"):
# 		frappe.logger("zra_sync").warning(
# 			f"Skipping revision credit — invoice {document_name} has no VSDC number."
# 		)
# 		return

# 	if not frappe.db.exists(doctype, reference_number):
# 		frappe.logger("zra_sync").warning(
# 			f"No revision record found for {reference_number}. Skipping credit."
# 		)
# 		return

# 	revision_doc = frappe.get_doc(doctype, reference_number)
# 	payload = build_credit_note_payload(revision_doc, settings_name)

# 	request_data = {
# 		"document_name": reference_number,
# 		"company": revision_doc.company,
# 		**payload,
# 	}

# 	def on_success(response, **_):
# 		if response.get("IsSuccess"):
# 			frappe.logger("zra_sync").info(f"Successfully credited revision {reference_number} in ZRA.")
# 			revision_doc.db_set("custom_zra_status", "Credited", update_modified=False)
# 		else:
# 			frappe.logger("zra_sync").error(
# 				f"Failed to credit revision {reference_number}: {response.get('ErrorMessage')}"
# 			)

# 	def on_error(error):
# 		frappe.log_error(
# 			title="ZRA Revision Credit Error",
# 			message=f"Failed to credit invoice revision {reference_number}: {error}",
# 		)

# 	process_request(
# 		request_data=request_data,
# 		route_key="SaveCreditNote",
# 		handler_function=on_success,
# 		doctype=doctype,
# 		settings_name=settings_name,
# 		company=revision_doc.company,
# 		error_callback=on_error,
# 		document_name=reference_number,
# 	)


# def resend_invoice(document_name: str, doctype: str) -> None:
# 	"""
# 	Fallback resend logic if invoice response is empty or incomplete.
# 	"""
# 	doc = frappe.get_doc(doctype, document_name)
# 	frappe.logger("zra_sync").warning(f"Resending invoice {document_name} to ZRA...")
# 	generic_invoices_on_submit_override(doc, docty)
