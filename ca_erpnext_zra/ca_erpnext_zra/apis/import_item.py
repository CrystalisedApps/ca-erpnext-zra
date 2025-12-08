import json
from datetime import datetime

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date

from ..apis.api_processor import process_request
from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME, COUNTRY_DOCTYPE_NAME
from ..handlers.import_item_handler import imported_items_select_on_success
from ..utils.payload_utils import build_import_item_payload
from ..utils.routes_utils import get_route_path


@frappe.whitelist()
def select_import_items(company_name: str, branch_name: str) -> None:
	credential = frappe.db.get_value(
		SETTINGS_DOCTYPE_NAME, {"company_name": company_name}, ["name", "company_name", "tpin"], as_dict=True
	)

	if not credential:
		frappe.throw(f"No Active {SETTINGS_DOCTYPE_NAME} found.")

	branch_code = frappe.db.get_value("Branch", {"name": branch_name}, "custom_branch_code")

	route_key = "selectImports"

	request_data = build_import_item_payload(credential)
	_, last_req_date = get_route_path(route_key, "Crystal VSDC")
	request_date = add_to_date(datetime.now(), years=-1).strftime("%Y%m%d%H%M%S")
	last_req_date = last_req_date.strftime("%Y%m%d%H%M%S") if last_req_date else request_date
	request_data.update({"lastReqDt": last_req_date, "bhfId": branch_code})
	perform_import_item(request_data, credential.name, route_key)


def perform_import_item(request_data: str, settings_name: str, route_key: str):
	process_request(
		request_data,
		route_key,
		imported_items_select_on_success,
		request_method="POST",
		doctype="Item",
		settings_name=settings_name,
		bhfid=request_data.get("bhfId"),
	)


@frappe.whitelist()
def create_item_from_fetched_registered_import(request_data: str) -> None:
	data = json.loads(request_data)
	if data["items"]:
		items = data["items"]
		for item in items:
			get_or_create_item(item)


def get_or_create_item(data: dict) -> Document:
	if frappe.db.exists("Item", {"item_code": data["item_name"]}):
		return frappe.get_doc("Item", {"item_code": data["item_name"]})
	else:
		new_item = frappe.new_doc("Item")
		new_item.is_stock_item = 0  # Default to 0
		new_item.item_code = data.get("item_name")
		new_item.item_name = data.get("item_name")
		new_item.item_group = "All Item Groups"
		new_item.custom_smart_packaging_unit = data.get("packaging_unit_code")
		new_item.custom_smart_quantity_unit = data.get("quantity_unit_code")
		new_item.custom_hs_code = data.get("hs_code")
		new_item.custom_imported_item_task_code = data.get("task_code")
		new_item.custom_imported_item_status = data.get("imported_item_status")
		new_item.custom_imported_item_status_code = data.get("imported_item_status_code")
		new_item.custom_smart_country_of_origin_ = data.get("origin_nation_code")
		new_item.custom_smart_country_of_origin_name = (
			frappe.get_doc(
				COUNTRY_DOCTYPE_NAME,
				{"code": data["origin_nation_code"]},
				for_update=False,
			).code_name
			if data["origin_nation_code"]
			else None
		)
		new_item.valuation_rate = data["unit_price"]

		if "imported_item" in data:
			new_item.is_stock_item = 1
			new_item.custom_referenced_imported_item = data["imported_item"]

		new_item.insert(ignore_mandatory=True, ignore_if_duplicate=True)
		return new_item
