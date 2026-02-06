import frappe

from ..services.sales_service import submit_credit_note_service


@frappe.whitelist()
def submit_credit_note(document_name: str, doctype: str, settings_name: str) -> None:
	"""
	API endpoint to submit a Credit Note to Crystal VSDC.
	"""
	submit_credit_note_service(document_name, doctype, settings_name)


@frappe.whitelist()
def get_principals(settings_name: str) -> None:
	"""
	API endpoint to fetch Principals from Crystal VSDC.
	"""
	from ..apis.api_processor import process_request
	from ..utils.settings_utils import get_settings
	from ..utils.routes_utils import get_route_path
	from datetime import datetime
	from frappe.utils import add_to_date

	settings = get_settings(settings_name)
	if not settings:
		frappe.throw("Settings not found")

	tpin = settings.get("tpin")
	# bhfId is often branch specific, but for now taking from settings or default "000"
	bhfId = "000" 
	
	# Logic to get last request date or default to 1 year ago
	route_key = "selectPrincipals"
	_, last_req_date = get_route_path(route_key, "Crystal VSDC")
	
	if last_req_date:
		lastReqDt = last_req_date.strftime("%Y%m%d%H%M%S")
	else:
		lastReqDt = add_to_date(datetime.now(), years=-1).strftime("%Y%m%d%H%M%S")

	payload = {
		"tpin": tpin,
		"bhfId": bhfId,
		"lastReqDt": lastReqDt
	}

	return process_request(
		request_data=payload,
		route_key=route_key,
		request_method="POST",
		settings_name=settings_name
	)
