import json

import frappe
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, nowdate, today

from ..apis.item_api import perform_item_registration
from ..doctype.doctype_names_mapping import (
	COUNTRY_DOCTYPE_NAME,
	ITEM_CLASSIFICATIONS_DOCTYPE_NAME,
	REGISTERED_PURCHASE_ITEM_CHILD,
	REGISTERED_PURCHASES_DOCTYPE_NAME,
)


def purchase_search_on_success(response: dict, **kwargs) -> None:
	sales_list = response.get("Result", {}).get("data", {}).get("saleList", [])

	if not sales_list:
		frappe.log_error(
			message=f"No purchases found in response: {response}", title="Smart Purchase Fetch Empty"
		)
		return

	for sale in sales_list:
		created_record = create_purchase_from_smart_search_details(sale)

		for item in sale.get("itemList", []):
			create_and_link_purchase_item(item, created_record)


def create_purchase_from_smart_search_details(fetched_purchase: dict) -> str:
	"""
	Create or update a 'Smart Registered Purchase' document in ERPNext.
	Items are handled separately by create_and_link_purchase_item().
	"""

	purchase_id = (
		f"{fetched_purchase['spplrTpin']}-{fetched_purchase['spplrBhfId']}-{fetched_purchase['spplrInvcNo']}"
	)

	existing_doc = frappe.get_value(REGISTERED_PURCHASES_DOCTYPE_NAME, {"purchase_id": purchase_id}, "name")

	doc = (
		frappe.get_doc(REGISTERED_PURCHASES_DOCTYPE_NAME, existing_doc)
		if existing_doc
		else frappe.new_doc(REGISTERED_PURCHASES_DOCTYPE_NAME)
	)

	# Safe flags
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate_update_after_submit = True
	doc.purchase_id = purchase_id

	# Basic fields
	doc.receipt_type_code = fetched_purchase.get("rcptTyCd")
	doc.pchstycd = "N"
	doc.regtycd = "A"
	doc.pchssttscd = "02"

	doc.receipt_type = frappe.db.get_value(
		"Crystallised Smart Purchase Receipt Type", {"code": doc.receipt_type_code}, "code_name"
	)

	doc.registration_type = "Automatic"
	doc.purchase_status = frappe.db.get_value(
		"Crystallised Smart Purchase Status", {"code": doc.pchssttscd}, "code_name"
	)

	# Supplier & purchase info
	doc.supplier_name = fetched_purchase.get("spplrNm")
	doc.supplier_tpin = fetched_purchase.get("spplrTpin")
	doc.supplier_branch_id = fetched_purchase.get("spplrBhfId")
	doc.supplier_invoice_no = fetched_purchase.get("spplrInvcNo")
	doc.payment_type_code = fetched_purchase.get("pmtTyCd")
	doc.remark = fetched_purchase.get("remark")

	# Dates
	try:
		if fetched_purchase.get("cfmDt"):
			doc.confirmed_date = get_datetime(fetched_purchase["cfmDt"])
	except Exception:
		doc.confirmed_date = None

	try:
		if fetched_purchase.get("salesDt"):
			sales_dt = fetched_purchase["salesDt"]
			doc.sales_date = get_datetime(f"{sales_dt[:4]}-{sales_dt[4:6]}-{sales_dt[6:8]}")
	except Exception:
		doc.sales_date = None

	try:
		if fetched_purchase.get("stockRlsDt"):
			doc.stock_release_date = get_datetime(fetched_purchase["stockRlsDt"])
	except Exception:
		doc.stock_release_date = None

	# Totals
	doc.total_item_count = fetched_purchase.get("totItemCnt", 0)
	doc.total_taxable_amount = fetched_purchase.get("totTaxblAmt", 0.0)
	doc.total_tax_amount = fetched_purchase.get("totTaxAmt", 0.0)
	doc.total_amount = fetched_purchase.get("totAmt", 0.0)

	# Clear child table
	doc.items = []

	# Save & submit
	doc.save(ignore_permissions=True)
	if doc.docstatus != 1:
		doc.submit()

	return doc.name


def create_and_link_purchase_item(item: dict, parent_record: str) -> None:
	"""
	Append an item to Registered Purchase DocType safely.
	"""

	parent = frappe.get_doc(REGISTERED_PURCHASES_DOCTYPE_NAME, parent_record)
	parent.flags.ignore_permissions = True
	parent.flags.ignore_validate_update_after_submit = True

	# --------------------------
	# 1. Ensure classification exists
	# --------------------------
	item_cls_code = item.get("itemClsCd") or "99999999"
	# frappe.throw(str(item_cls_code))
	classification_doc = frappe.db.exists(ITEM_CLASSIFICATIONS_DOCTYPE_NAME, item_cls_code)

	if not classification_doc:
		cls = frappe.new_doc(ITEM_CLASSIFICATIONS_DOCTYPE_NAME)
		vat_category = item.get("vatCatCd", "").strip().upper()

		# Avoid failing when the linked record doesn't exist
		if vat_category and frappe.db.exists("Crystallised ZRA Smart Taxation Type", vat_category):
			cls.tax_ty_cd = vat_category
		else:
			cls.tax_ty_cd = None
		cls.item_cls_cd = item_cls_code
		# better mapping
		cls.save()
		classification_doc = cls.name

	# --------------------------
	# 2. Append child row
	# --------------------------

	parent.append(
		"items",
		{
			"item_seq": item.get("itemSeq"),
			"item_name": item.get("itemNm"),
			"item_code": item.get("itemCd") or f"TEMP-{item.get('itemSeq', 'X')}",
			# IMPORTANT — use the REAL child table fieldname
			"item_class_code": item.get("itemClsCd"),
			"packaging_unit_code": item.get("pkgUnitCd"),
			"quantity": flt(item.get("qty") or 1),
			"quantity_unit_code": item.get("qtyUnitCd"),
			"unit_price": flt(item.get("prc") or 0),
			"supply_amount": flt(item.get("splyAmt") or 0),
			"discount_rate": flt(item.get("dcRt") or 0),
			"discount_amount": flt(item.get("dcAmt") or 0),
			"vat_category_code": item.get("vatCatCd"),
			"taxable_amount": flt(item.get("taxblAmt") or 0),
			"vat_amount": flt(item.get("vatAmt") or 0),
			"total_amount": flt(item.get("totAmt") or 0),
		},
	)

	# --------------------------
	# 3. Save parent
	# --------------------------
	parent.save(ignore_permissions=True)
	frappe.db.commit()


def _update_parent_link_status(parent_doc):
	"""
	Update parent doc counters and if all items linked mark linked_all_items flag.
	Assumes parent_doc has fields:
	  - total_item_count
	  - linked_item_count (int)
	  - linked_all_items (checkbox)
	"""
	# compute linked count
	linked_count = len(getattr(parent_doc, REGISTERED_PURCHASE_ITEM_CHILD, []) or [])
	parent_doc.linked_item_count = linked_count

	try:
		total_expected = int(parent_doc.total_item_count or 0)
	except Exception:
		total_expected = 0

	parent_doc.linked_all_items = linked_count >= total_expected and total_expected > 0
	parent_doc.save(ignore_permissions=True)
	frappe.db.commit()


# def create_or_update_purchase_invoice_from_smart(doc):
#     """
#     Create or update a Purchase Invoice in ERPNext based on Smart (ZRA) data.
#     Safe against missing fields, orphaned child rows, and validation edge cases.
#     """

#     supplier_name = get_or_create_supplier_from_smart(doc)

#     existing_pi = frappe.db.get_value(
#         "Purchase Invoice",
#         {"custom_smart_purchase_id": doc.purchase_id or doc.smart_id},
#         "name"
#     )

#     if existing_pi:
#         #  Update existing invoice
#         pi = frappe.get_doc("Purchase Invoice", existing_pi)
#         pi.set("items", [])  # clear all previous rows safely
#     else:
#         #  Create new invoice
#         pi = frappe.new_doc("Purchase Invoice")
#         pi.custom_smart_purchase_id = doc.purchase_id or doc.smart_id
#         pi.company = getattr(doc, "company", frappe.defaults.get_user_default("Company"))
#         pi.supplier = supplier_name
#         pi.bill_no = getattr(doc, "supplier_invoice_no", None) or getattr(doc, "spplrInvcNo", None)
#         pi.bill_date = getattr(doc, "salesDt", today())
#         pi.posting_date = today()
#         pi.currency = "ZMW"  # or derive from Smart if available
#         pi.buying_price_list = frappe.db.get_value("Buying Settings", None, "price_list") or "Standard Buying"

#     # ---  Add Items ---
#     for item in getattr(doc, "items", []):
#         item_code = get_or_create_item_from_smart(item)

#         qty = flt(getattr(item, "qty", 1))
#         rate = flt(getattr(item, "prc", 0.0))
#         amount = qty * rate
#         uom = getattr(item, "qtyUnitCd", "Nos") or "Nos"
#         conversion_factor = 1.0
#         stock_qty = qty * conversion_factor

#         # Get a valid default expense account
#         default_expense_account = (
#             frappe.db.get_value("Company", pi.company, "default_expense_account")
#             or frappe.db.get_value("Company", pi.company, "stock_received_but_not_billed")
#             or frappe.db.get_value("Account", {"company": pi.company, "root_type": "Expense"}, "name")
#         )
#         pi.append("items", {
#             "item_code": item_code,
#             "item_name": getattr(item, "itemNm", item_code),
#             "description": getattr(item, "itemNm", item_code),
#             "qty": qty,
#             "stock_uom": uom,
#             "uom": uom,
#             "conversion_factor": conversion_factor,
#             "stock_qty": stock_qty,
#             "accepted_qty": qty,
#             "rate": rate,
#             "amount": amount,
#             "base_rate": rate,
#             "base_amount": amount,
#             "received_qty": qty,
#             "warehouse": frappe.db.get_value("Warehouse", {"company": pi.company}, "name") or "Main Warehouse",
#            "expense_account": default_expense_account,   #  Fix: ensure valid expense account

#         })

#     # ---  Force new child inserts (avoid old row references) ---
#     for row in pi.items:
#         row.name = None

#     # --- Safety Flags ---
#     pi.flags.ignore_permissions = True
#     pi.flags.ignore_validate_update_after_submit = True
#     pi.flags.ignore_mandatory = True
#     pi.flags.ignore_links = True
#     pi.flags.ignore_validate = True

#     # ---  Save Safely ---
#     pi.save(ignore_permissions=True)
#     frappe.db.commit()

#     # ---  Optional: auto-submit if valid ---
#     try:
#         if not pi.docstatus:
#             pi.submit()
#             frappe.db.commit()
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), f"Smart Purchase: failed to submit {pi.name}")

#     return pi.name


# ------------------- Utility Functions -------------------


def get_default_company() -> str:
	company = frappe.defaults.get_user_default("Company")
	if not company:
		company = frappe.db.get_single_value("Global Defaults", "default_company")
	return company


def get_default_warehouse() -> str:
	return frappe.db.get_value("Warehouse", {"is_group": 0}, "name")


def get_default_cost_center() -> str:
	return frappe.db.get_value("Cost Center", {"is_group": 0}, "name")


@frappe.whitelist()
def create_items_from_smart_purchase(request_data: str) -> None:
	"""
	Create Items in ERPNext from ZRA Smart Invoice purchase data.
	This can be called via Frappe call from a custom doctype (like Registered Purchases).
	"""
	if isinstance(request_data, str):
		data = json.loads(request_data)
	else:
		data = request_data

	items = data.get("items") or []
	if not items:
		frappe.msgprint("No items found in Smart Purchase data.")
		return

	created_items = []
	for item in items:
		item_name = get_or_create_item_from_smart(item)
		created_items.append(item_name)

	frappe.msgprint(f"Created or linked {len(created_items)} Smart items.")


def get_or_create_item_from_smart(item_row) -> str:
	"""
	Normalized Item creator for ZRA Smart purchase items.
	Supports SmartRegisteredPurchaseItem, dict, frappe._dict.
	"""

	# ----------------------------
	# Helper for safe extraction
	# ----------------------------
	def val(*keys, default=None):
		for key in keys:
			if hasattr(item_row, key):
				v = getattr(item_row, key, None)
				if v not in (None, "", "0"):
					return v
			if isinstance(item_row, (dict, frappe._dict)):
				v = item_row.get(key)
				if v not in (None, "", "0"):
					return v
		return default

	# ----------------------------
	# Extract Item Code
	# ----------------------------
	item_code = val("itemCd", "prdCode", "product_code", "item_code", default=None)

	if not item_code:
		frappe.throw(f"Item code missing in Smart item: {item_row}")

	# ----------------------------
	# Item Name
	# ----------------------------
	item_name = val("itemNm", "prdNm", "item_name", default="Unnamed Item")

	# ----------------------------
	# Units (UOM)
	# ----------------------------
	packaging_unit = val("pkgUnitCd", "packaging_unit_code", default="EA")
	quantity_unit = val("qtyUnitCd", "quantity_unit_code", "unit_of_quantity_code", default="Nos")

	ensure_uom_exists(quantity_unit)
	ensure_uom_exists(packaging_unit)

	# ----------------------------
	# VAT / Taxation Code (REAL FIX)
	# Smart API sends: taxTyCd
	# Sometimes vatCatCd is used in ERPNext custom fields.
	# ----------------------------
	taxation_type = val("vatCatCd", "taxTyCd", "taxation_type_code", "vat_category_code", default="A")

	# ----------------------------
	# Classification Code
	# ----------------------------
	class_code = val("itemClsCd", "item_class_code", "item_classification_code", default=None)

	# ----------------------------
	# Unit Price
	# ----------------------------
	unit_price = val("prc", "unit_price", default=0.0)

	# ----------------------------
	# Check existing Item
	# ----------------------------
	existing_item = frappe.db.exists("Item", {"item_code": item_code})
	if existing_item:
		return existing_item

	# ----------------------------
	# Create new Item
	# ----------------------------
	new_item = frappe.new_doc("Item")
	new_item.item_code = item_code
	new_item.item_name = item_name
	new_item.item_group = "Products"
	new_item.stock_uom = quantity_unit

	# ----------------------------
	# CUSTOM SMART FIELDS (FIXED)
	# ----------------------------
	new_item.custom_smart_item_code = item_code
	new_item.custom_smart_item_classification_code = class_code
	new_item.custom_smart_packaging_unit = packaging_unit
	new_item.custom_smart_quantity_unit = quantity_unit
	new_item.custom_vat_category_code = taxation_type

	# ----------------------------
	# Country of Origin (first 2 chars)
	# ----------------------------
	try:
		if len(item_code) >= 2:
			country = frappe.get_doc(COUNTRY_DOCTYPE_NAME, {"code": item_code[:2]})
			new_item.custom_smart_country_of_origin_ = country.name
		else:
			new_item.custom_smart_country_of_origin_ = None
	except Exception:
		new_item.custom_smart_country_of_origin_ = None

	# ----------------------------
	# Item Type (3rd digit)
	# ----------------------------
	new_item.custom_smart_item_type = item_code[2:3] if item_code else None

	if item_code and int(item_code[2:3]) != 3:
		new_item.is_stock_item = 1
	else:
		new_item.is_stock_item = 0

	# ----------------------------
	# Pricing
	# ----------------------------
	new_item.standard_rate = unit_price
	new_item.valuation_rate = unit_price

	# ----------------------------
	# Insert Item
	# ----------------------------
	new_item.insert(
		ignore_mandatory=True,
		ignore_if_duplicate=True,
		ignore_permissions=True,
	)

	return new_item.name


@frappe.whitelist()
def process_single_item(record: str) -> None:
	"""
	Process a single item for registration, construct the payload, and perform registration.

	Args:
	    record (str): Name of the item to process.
	"""
	item = frappe.get_doc("Item", record, for_update=False)

	valuation_rate = item.valuation_rate if item.valuation_rate is not None else 0

	perform_item_registration(item)


def ensure_uom_exists(uom_name: str):
	"""Ensure a UOM record exists before linking (Smart often sends unit codes dynamically)."""
	if not uom_name:
		return
	if not frappe.db.exists("UOM", uom_name):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom_name, "enabled": 1}).insert(ignore_permissions=True)


def get_or_create_supplier_from_smart(sale_data) -> str:
	"""
	Ensure a Supplier exists for the Smart (ZRA) purchase record.
	Handles both dicts and Frappe Document types like CrystallisedZRASmartPurchases.
	"""

	def val(fieldname, default=None):
		"""Safely extract field from dict, frappe._dict, or Document."""
		if hasattr(sale_data, fieldname):
			return getattr(sale_data, fieldname, default)
		if isinstance(sale_data, (dict, frappe._dict)):
			return sale_data.get(fieldname, default)
		return default

	#  Extract supplier details from Smart purchase data
	supplier_name = (
		val("supplier_name") or val("seller_name") or val("supplierNm") or val("suppNm") or "Unknown Supplier"
	)

	supplier_tpin = val("supplier_tpin") or val("seller_tpin") or val("suppTpin") or val("tpin") or ""

	supplier_branch_id = val("supplier_branch_id") or val("branch_id") or ""
	supplier_country = val("supplier_country") or val("country") or "Zambia"
	supplier_currency = val("supplier_currency") or "ZMW"

	# Normalize values
	supplier_name = supplier_name.strip() if supplier_name else "Unknown Supplier"
	supplier_tpin = supplier_tpin.strip() if supplier_tpin else ""

	#  Prefer to match by TPIN if available
	existing_supplier = None
	if supplier_tpin:
		existing_supplier = frappe.db.exists("Supplier", {"tax_id": supplier_tpin})

	# fallback match by name if TPIN is missing
	if not existing_supplier and supplier_name:
		existing_supplier = frappe.db.exists("Supplier", {"supplier_name": supplier_name})

	if existing_supplier:
		return existing_supplier

	#  Create a new Supplier
	new_supplier = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": supplier_name,
			"supplier_group": "All Supplier Groups",
			"tax_id": supplier_tpin,
			"supplier_type": "Company",
			"default_currency": supplier_currency,
			"country": supplier_country,
		}
	)

	# Optional custom field for ZRA branch ID (if your doctype has it)
	if frappe.db.has_column("Supplier", "custom_supplier_branch_id"):
		new_supplier.custom_supplier_branch_id = supplier_branch_id

	new_supplier.insert(ignore_permissions=True)
	frappe.db.commit()

	return new_supplier.name
