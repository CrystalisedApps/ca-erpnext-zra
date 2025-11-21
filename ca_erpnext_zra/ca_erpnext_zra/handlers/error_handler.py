import json

import frappe
from frappe.model.document import Document

from ..logger import smart_logger
from ..utils.routes_utils import update_last_request_date


def handle_errors(
	response: dict[str, str],
	route: str,
	document_name: str,
	doctype: str | Document | None = None,
	integration_request_name: str | None = None,
) -> None:
	if not response:
		return ("Empty response from API", "NO_RESPONSE")

	# Parse string JSON
	if isinstance(response, str):
		try:
			response = json.loads(response)
		except Exception:
			# raw HTML / text error
			return (response, "INVALID_JSON")

	# Now response is a dict
	error_message = (
		response.get("resultMsg")
		or response.get("message")
		or response.get("error")
		or response.get("msg")
		or "Unknown API Error"
	)

	error_code = (
		response.get("resultCd") or response.get("status") or response.get("code") or "UNKNOWN_ERROR_CODE"
	)

	smart_logger.error("%s, Code: %s" % (error_message, error_code))

	try:
		frappe.throw(
			error_message,
			frappe.InvalidStatusError,
			title=f"Error: {error_code}",
		)

	except frappe.InvalidStatusError as error:
		frappe.log_error(
			frappe.get_traceback(with_context=True),
			error,
			reference_name=document_name,
			reference_doctype=doctype,
		)
		raise

	finally:
		update_last_request_date(response["resultDt"], route)
