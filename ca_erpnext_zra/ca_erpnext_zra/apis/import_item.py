import json

import frappe
from frappe.utils import now_datetime

from ..apis.api_processor import process_request
from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME
from ..handlers.import_item_handler import imported_items_select_on_success
from ..utils.payload_utils import build_import_item_payload
from ..utils.routes_utils import get_route_path


@frappe.whitelist()
def select_import_items_all_branches() -> None:
	all_credentials = frappe.get_all(
		SETTINGS_DOCTYPE_NAME, ["name", "company_name", "tpin"], {"is_active": 1}
	)

	if len(all_credentials) < 1:
		frappe.throw(f"No Active {SETTINGS_DOCTYPE_NAME} found.")

	route_key = "selectImports"

	for cred in all_credentials:
		request_data = build_import_item_payload(cred)

		_, last_req_date = get_route_path(route_key, "Crystal VSDC")
		last_req_date = (
			last_req_date.strftime("%Y%m%d%H%M%S")
			if last_req_date
			else now_datetime().strftime("%Y%m%d%H%M%S")
		)
		request_data.update({"lastReqDt": "20231215000000"})
		perform_import_item(request_data, cred.name, route_key)


def perform_import_item(request_data: str, settings_name: str, route_key: str):
	process_request(
		request_data,
		route_key,
		imported_items_select_on_success,
		request_method="POST",
		doctype="Item",
		settings_name=settings_name,
	)
