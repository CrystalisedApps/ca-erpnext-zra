from datetime import datetime

import frappe

from ..doctype.doctype_names_mapping import (
	COUNTRY_DOCTYPE_NAME,
	IMPORTED_ITEMS_STATUS_DOCTYPE_NAME,
	PACKAGING_UNIT_DOCTYPE_NAME,
	REGISTERED_IMPORTED_ITEM_DOCTYPE_NAME,
	UNIT_OF_QUANTITY_DOCTYPE_NAME,
)
from ..utils.smart_api_utils import get_link_value, get_or_create_link


def imported_items_select_on_success(response: dict, settings_name: str, **kwargs) -> None:
	items = response.get("Result", {}).get("data", {}).get("itemList", [])
	batch_size = 20
	counter = 0

	if not items:
		return

	for item in items:
		try:
			item_id = f"{item.get('itemSeq')}{item.get('dclDe')}{item.get('taskCd')}"
			existing_item = frappe.db.get_value(
				REGISTERED_IMPORTED_ITEM_DOCTYPE_NAME,
				{"item_identifier": item_id},
				"name",
				order_by="creation desc",
			)

			if existing_item:
				continue

			response_data = {
				"item_identifier": item_id,
				"item_name": item.get("itemNm"),
				"task_code": item.get("taskCd"),
				"declaration_date": parse_date(item.get("dclDe")),
				"item_sequence": item.get("itemSeq"),
				"declaration_number": item.get("dclNo"),
				"declaration_reference_number": item.get("dclRefNum"),
				"imported_item_status_code": item.get("imptItemsttsCd"),
				"imported_item_status": get_link_value(
					IMPORTED_ITEMS_STATUS_DOCTYPE_NAME,
					"code",
					item.get("imptItemsttsCd"),
				),
				"hs_code": item.get("hsCd"),
				"origin_nation_code": get_link_value(COUNTRY_DOCTYPE_NAME, "code", item.get("orgnNatCd")),
				"export_nation_code": get_link_value(COUNTRY_DOCTYPE_NAME, "code", item.get("exptNatCd")),
				"package": item.get("pkg"),
				"packaging_unit_code": get_or_create_link(
					PACKAGING_UNIT_DOCTYPE_NAME, "code", item.get("pkgUnitCd")
				),
				"quantity": item.get("qty"),
				"quantity_unit_code": get_or_create_link(
					UNIT_OF_QUANTITY_DOCTYPE_NAME,
					"code",
					item.get("qtyUnitCd"),
				),
				"gross_weight": item.get("totWt"),
				"net_weight": item.get("netWt"),
				"suppliers_name": item.get("spplrNm"),
				"agent_name": item.get("agntNm"),
				"invoice_foreign_currency_amount": item.get("invcFcurAmt"),
				"invoice_foreign_currency": item.get("invcFcurCd"),
				"foreign_currency_exchange_rate": item.get("invcFcurExcrt"),
				"settings": settings_name,
			}

			# if existing_item:
			# 	item_doc = frappe.get_doc(REGISTERED_IMPORTED_ITEM_DOCTYPE_NAME, existing_item)
			# 	item_doc.update(response_data)
			# 	item_doc.flags.ignore_mandatory = True
			# 	item_doc.save(ignore_permissions=True)
			# else:
			# 	item_doc = frappe.get_doc({"doctype": REGISTERED_IMPORTED_ITEM_DOCTYPE_NAME, **response_data})
			# 	item_doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_if_duplicate=True)

			item_doc = frappe.get_doc({"doctype": REGISTERED_IMPORTED_ITEM_DOCTYPE_NAME, **response_data})
			item_doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_if_duplicate=True)

			# item_name = item.get("itemNm")
			# if not item_name:
			# 	continue

			# item_code = f"{item.get('orgnNatCd')}{item.get('pkgUnitCd')}{item.get('qtyUnitCd')}"
			# item_name = item.get("itemNm")

			# if frappe.db.exists("Item", {"item_code": item_code}):
			# 	product = frappe.get_doc("Item", {"item_code": item_code})
			# else:
			# 	product = frappe.new_doc("Item")
			# 	product.item_code = item_code
			# 	product.item_name = item_name
			# 	default_item_group = frappe.get_all(
			# 		"Item Group", filters={"is_group": 1}, fields=["name"], limit=1
			# 	)
			# 	product.item_group = default_item_group[0].name if default_item_group else "All Item Groups"
			# 	product.flags.ignore_mandatory = True
			# 	product.insert(ignore_permissions=True)

			# product_name = None
			# if frappe.db.exists(
			# 	SMART_CRYSTALLISED_MAPPING_DOCTYPE_NAME,
			# 	{"zra_item_code": item_name, "smart_setup": settings_name},
			# ):
			# 	product_name = frappe.db.get_value(
			# 		SMART_CRYSTALLISED_MAPPING_DOCTYPE_NAME,
			# 		{"zra_item_code": item_name, "smart_setup": settings_name},
			# 		"parent",
			# 		order_by="creation desc",
			# 	)
			# 	product = frappe.get_doc("Item", product_name)

			# else:
			# 	if frappe.db.exists("Item", {"item_code": item_name}):
			# 		product = frappe.get_doc("Item", {"item_code": item_name})
			# 	else:
			# 		product = frappe.new_doc("Item")
			# 		product.item_name = item_name
			# 		product.item_code = item_name
			# 		default_item_group = frappe.get_all(
			# 			"Item Group", filters={"is_group": 1}, fields=["name"], limit=1
			# 		)
			# 		product.item_group = (
			# 			default_item_group[0].name if default_item_group else "All Item Groups"
			# 		)
			# 		product.flags.ignore_mandatory = True
			# 		product.insert(ignore_permissions=True)
			# 	frappe.get_doc(
			# 		{
			# 			"doctype": SMART_CRYSTALLISED_MAPPING_DOCTYPE_NAME,
			# 			"parent": product.name,
			# 			"parenttype": "Item",
			# 			"parentfield": "custom_smart_setup_mapping",
			# 			"zra_item_code": item_name,
			# 			"smart_setup": settings_name,
			# 		}
			# 	).insert(ignore_permissions=True)

			# update_data = {
			# 	"custom_referenced_imported_item": item_doc.name,
			# 	"custom_imported_item_task_code": item_doc.task_code,
			# 	"custom_hs_code": item_doc.hs_code,
			# 	"custom_imported_item_status": item_doc.imported_item_status,
			# 	"custom_imported_item_status_code": item_doc.imported_item_status_code,
			# 	"is_stock_item": 1,
			# }
			# frappe.db.set_value("Item", product.name, update_data, update_modified=False)

			counter += 1
			if counter % batch_size == 0:
				frappe.db.commit()
				frappe.logger().info(f"Committed batch of {batch_size} items")

		except Exception as e:
			raise e

	if counter % batch_size != 0:
		frappe.db.commit()

	frappe.msgprint(
		"Imported Items fetched successfully. Go to <b>Crystallised Smart Registered Import Item</b> Doctype for more information."
	)


def parse_date(date_str: str) -> None:
	formats = [
		"%d%m%Y",
		"%Y-%m-%d",
		"%d-%m-%Y",
		"%m/%d/%Y",
		"%d/%m/%Y",
		"%Y/%m/%d",
		"%B %d, %Y",
		"%b %d, %Y",
		"%Y.%m.%d",
	]
	for fmt in formats:
		try:
			return datetime.strptime(date_str, fmt)
		except ValueError:
			continue
	if date_str.isdigit():
		try:
			return datetime.fromtimestamp(int(date_str))
		except ValueError:
			pass
	raise ValueError(f"Invalid date format: {date_str}")
