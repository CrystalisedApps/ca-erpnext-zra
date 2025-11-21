import json

import frappe
from frappe.utils import get_link_to_form

from ..utils.create_supplier import get_or_create_supplier
from .import_item import get_or_create_item


@frappe.whitelist()
def create_purchase_invoice_from_request(request_data: str) -> None:
	data = json.loads(request_data)

	supplier = None
	if not frappe.db.exists("Supplier", data["supplier_name"]):
		supplier = get_or_create_supplier(data).name

	if frappe.db.exists("Purchase Invoice", {"custom_import_source_registered_purchase": data["name"]}):
		return

	all_existing_items = {item["name"]: item for item in frappe.db.get_all("Item", ["*"])}

	for received_item in data["items"]:
		# Check if item exists
		if received_item["item_name"] not in all_existing_items:
			_ = get_or_create_item(received_item)

	# Create the Purchase Invoice
	purchase_invoice = frappe.new_doc("Purchase Invoice")
	purchase_invoice.supplier = supplier or data["supplier_name"]
	purchase_invoice.update_stock = 1
	purchase_invoice.bill_no = data["supplier_invoice_no"]
	purchase_invoice.bill_date = data["supplier_invoice_date"]
	purchase_invoice.custom_import_source_registered_purchase = data["name"]
	purchase_invoice.custom_smart_purchase_id = data["name"]
	if "currency" in data:
		# The "currency" key is only available when creating from Imported Item
		purchase_invoice.currency = data["currency"]
		# purchase_invoice.custom_source_registered_imported_item = data["name"]

	if "exchange_rate" in data:
		purchase_invoice.conversion_rate = data["exchange_rate"]

	purchase_invoice.set("items", [])

	company_name = data["company_data"]["responseJSON"]["message"]["company_name"]
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

	if item_doc.custom_referenced_imported_item and (
		item_doc.custom_item_registered == 0 or item_doc.custom_imported_item_submitted == 0
	):
		item_link = get_link_to_form("Item", item_doc.name)
		frappe.throw(f"Register or submit the item: {item_link}")

	elif not item_doc.custom_referenced_imported_item and item_doc.custom_item_registered == 0:
		item_link = get_link_to_form("Item", item_doc.name)
		frappe.throw(f"Register the item: {item_link}")


def update_registered_import_item(request_data: list) -> None:
	pass
