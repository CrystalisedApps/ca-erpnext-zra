import json
from datetime import datetime

import frappe
from frappe.utils import get_link_to_form

from ..utils.create_supplier import get_or_create_supplier
from .import_item import get_or_create_item
from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME, REGISTERED_IMPORTED_ITEM_DOCTYPE_NAME
from ..apis.api_processor import process_request
from ..handlers.import_item_handler import import_item_update_on_success


@frappe.whitelist()
def create_purchase_invoice_from_request(request_data: str) -> None:
	data = json.loads(request_data)

	supplier = None
	if not frappe.db.exists("Supplier", data["supplier_name"]):
		supplier = get_or_create_supplier(data).name

	if frappe.db.exists("Purchase Invoice", {"custom_import_source_registered_purchase": data["name"]}):
		frappe.throw("Purchase Invoice already exists for this registered import.")
		return

	all_existing_items = {item["name"]: item for item in frappe.db.get_all("Item", ["*"])}

	for received_item in data["items"]:
		# Check if item exists
		if received_item["item_name"] not in all_existing_items:
			_ = get_or_create_item(received_item)

	branch = frappe.db.get_value("Branch", {"custom_branch_code": data.get("branch_code")}, "name")

	# Create the Purchase Invoice
	purchase_invoice = frappe.new_doc("Purchase Invoice")
	purchase_invoice.supplier = supplier or data["supplier_name"]
	purchase_invoice.company = data["company_name"]
	purchase_invoice.branch = branch
	purchase_invoice.update_stock = 1
	purchase_invoice.bill_no = data["supplier_invoice_no"]
	purchase_invoice.bill_date = data["supplier_invoice_date"]
	purchase_invoice.custom_import_source_registered_purchase = data["name"]
	purchase_invoice.custom_smart_purchase_id = data["name"]
	purchase_invoice.credit_to = data.get("creditors_account")
	if "currency" in data:
		# The "currency" key is only available when creating from Imported Item
		purchase_invoice.currency = data["currency"]
		# purchase_invoice.custom_source_registered_imported_item = data["name"]

	if "exchange_rate" in data:
		purchase_invoice.conversion_rate = data["exchange_rate"]

	purchase_invoice.set("items", [])

	company_name = data["company_name"]
	company_abbr = frappe.get_value("Company", company_name, "abbr")
	expense_account = frappe.db.get_value(
		"Account",
		{
			"name": [
				"like",
				f"%Cost of Goods Sold%{company_abbr}",
			]
		},
		["name"],
	)

	for item in data["items"]:
		standard_item = frappe.db.get_all("Item", {"item_code": item["item_name"]}, ["*"])[0]
		purchase_invoice.append(
			"items",
			{
				"item_name": standard_item["item_name"],
				"item_code": standard_item["item_code"],
				"qty": item["quantity"],
				"rate": item["unit_price"],
				"expense_account": expense_account,
			},
		)
	validate_mapping_and_registration_of_items(data["items"])
	purchase_invoice.save()
	purchase_invoice.submit()

	frappe.msgprint("Purchase Invoices have been created")


def validate_mapping_and_registration_of_items(items):
	for item in items:
		item_name = item.get("item_name")
		items = frappe.get_all(
			"Item",
			filters={"item_code": item_name},
			fields=["name", "item_name", "item_code"],
		)
		if items:
			item_name = items[0].name

			validation_message(item_name)


def validation_message(item_code):
	item_doc = frappe.get_doc("Item", item_code)

	if item_doc.custom_referenced_imported_item and (item_doc.custom_item_registered == 0):
		item_link = get_link_to_form("Item", item_doc.name)
		frappe.throw(f"Register or submit the item: {item_link}")

	elif not item_doc.custom_referenced_imported_item and item_doc.custom_item_registered == 0:
		item_link = get_link_to_form("Item", item_doc.name)
		frappe.throw(f"Register the item: {item_link}")


@frappe.whitelist()
def update_registered_import_item(request_data: str) -> None:
	data = json.loads(request_data)

	tpin = frappe.db.get_value(SETTINGS_DOCTYPE_NAME, data.get("settings_name"), "tpin")

	if not tpin:
		frappe.log_error(
			f"TPIN not found in {SETTINGS_DOCTYPE_NAME} {data.get('settings_name')}.",
			"Update Registered Import Item",
		)
		return

	item_payload = []

	base_payload = {
		"tpin": tpin,
		"taskCd": data.get("task_code"),
		"bhfId": "000",
		"dclDe": datetime.strptime(data.get("declaration_date"), "%Y-%m-%d").strftime("%Y%m%d"),
	}

	try:
		item_doc = frappe.db.get_value(
			"Item",
			{"item_code": data.get("item_name")},
			[
				"custom_smart_item_classification_code",
				"custom_smart_item_code",
				"custom_hs_code",
			],
			as_dict=True,
		)
		if not item_doc:
			return

		item_payload.append(
			{
				"itemSeq": data.get("item_sequence"),
				"hsCd": data.get("hs_code") or item_doc.custom_hs_code,
				"itemClsCd": item_doc.custom_smart_item_classification_code,
				"itemCd": item_doc.custom_smart_item_code,
				"imptItemSttsCd": 3 if data.get("imported_item_status_code") == "Approved" else 4,
				"remark": None,
				"modrNm": data.get("modified_by"),
				"modrId": data.get("modified_by").split("@")[0] or "Admin",
			}
		)
	except Exception as e:
		frappe.log_error("Error processing item for Import Update:", str(e))

	if not item_payload:
		return

	final_payload = {**base_payload, "importItemList": item_payload}
	frappe.log_error("document_name", data.get("name"))

	frappe.enqueue(
		process_request,
		queue="long",
		timeout=60,
		is_async=True,
		job_name=f"update_imported_items_{data.get('task_code')}",
		request_data=final_payload,
		route_key="updateImports",
		request_method="POST",
		handler_function=import_item_update_on_success,
		doctype=REGISTERED_IMPORTED_ITEM_DOCTYPE_NAME,
		document_name=data.get("name"),
		settings_name=data.get("settings_name"),
	)
