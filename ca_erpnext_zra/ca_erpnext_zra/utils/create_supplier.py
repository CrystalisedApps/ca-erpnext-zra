import json

import frappe
from frappe.model.document import Document


@frappe.whitelist()
def create_supplier_from_fetched_registered_import(request_data: str) -> None:
	data = json.loads(request_data)

	new_supplier = get_or_create_supplier(data)

	frappe.msgprint(f"Supplier: {new_supplier.name} created successfully.")


def get_or_create_supplier(supplier_details: dict) -> Document:
	supplier_name = supplier_details.get("supplier_name")
	supplier_pin = supplier_details.get("supplier_pin")
	supplier_nation = supplier_details.get("supplier_nation", "").upper()
	import_item_id = supplier_details.get("name")
	
	# Generate supplier_name if not provided
	if not supplier_name:
		if supplier_pin:
			# Pattern: {country_code}-{supplier_pin}
			supplier_name = f"{supplier_nation}-{supplier_pin}"
		else:
			# Fallback: {country_code}-{import_item_id}
			supplier_name = f"{supplier_nation}-{import_item_id}"
	
	if frappe.db.exists("Supplier", {"name": supplier_name}):
		return frappe.get_doc("Supplier", {"name": supplier_name})
	else:
		new_supplier = frappe.new_doc("Supplier")

		new_supplier.supplier_name = supplier_name
		new_supplier.tax_id = supplier_pin or None

		if "supplier_currency" in supplier_details:
			new_supplier.default_currency = supplier_details["supplier_currency"]

		if "supplier_nation" in supplier_details:
			country = frappe.db.get_value(
				"Country", {"code": supplier_details["supplier_nation"].lower()}, "name"
			)
			new_supplier.country = country

		new_supplier.insert(ignore_if_duplicate=True)

		return new_supplier
