import json

import frappe
from frappe.model.document import Document


@frappe.whitelist()
def create_supplier_from_fetched_registered_import(request_data: str) -> None:
	data = json.loads(request_data)

	new_supplier = get_or_create_supplier(data)

	frappe.msgprint(f"Supplier: {new_supplier.name} created successfully.")


def get_or_create_supplier(supplier_details: dict) -> Document:
	if frappe.db.exists("Supplier", {"name": supplier_details["supplier_name"]}):
		return frappe.get_doc("Supplier", {"name": supplier_details["supplier_name"]})
	else:
		new_supplier = frappe.new_doc("Supplier")

		new_supplier.supplier_name = supplier_details["supplier_name"]
		new_supplier.tax_id = supplier_details["supplier_pin"]

		if "supplier_currency" in supplier_details:
			new_supplier.default_currency = supplier_details["supplier_currency"]

		if "supplier_nation" in supplier_details:
			country = frappe.db.get_value(
				"Country", {"code": supplier_details["supplier_nation"].lower()}, "name"
			)
			new_supplier.country = country

		new_supplier.insert(ignore_if_duplicate=True)

		return new_supplier
