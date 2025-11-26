import json
from datetime import datetime
from frappe.utils import add_to_date
import frappe
from frappe.model.document import Document

# from ..handlers.purchase_handlers import create_or_update_purchase_invoice_from_smart
from frappe.utils import flt, now_datetime, today
from frappe.utils.password import get_decrypted_password
from ..utils.routes_utils import get_route_path
from ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils import get_active_smart_settings

from ..apis.api_processor import process_request
from ..doctype.doctype_names_mapping import REGISTERED_PURCHASES_DOCTYPE_NAME
from ..handlers.invoice_handler import purchase_invoice_submission_on_success
from ..handlers.purchase_handlers import (
	get_or_create_item_from_smart,
	get_or_create_supplier_from_smart,
	purchase_search_on_success,
)
from ..utils.payload_utils import build_debit_note_payload, build_purchase_payload
from ..utils.settings_utils import get_settings


@frappe.whitelist()
def approve_smart_purchase(name):
	from ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api import create_purchase_invoice_from_smart_request

	doc = frappe.get_doc("Crystallised ZRA Smart Purchases", name)

	doc.purchase_status = "Approved"
	doc.pchsttscd = "02"
	doc.save(ignore_permissions=True)

	request_payload = frappe.as_json(doc.as_dict())

	create_purchase_invoice_from_smart_request(request_data=request_payload)

	frappe.msgprint(f"Purchase {name} has been approved and a Purchase Invoice created.")
	return True


@frappe.whitelist()
def create_purchase_invoice_from_smart_request(request_data: str) -> None:
	"""
	Creates or updates a Purchase Invoice in ERPNext from ZRA Smart Invoice data.
	Handles:
	- Existing submitted/cancelled invoices safely
	- Missing warehouses and accounts
	- Item creation and linking
	"""

	import json

	from frappe.utils import flt, today

	# Parse JSON
	data = json.loads(request_data) if isinstance(request_data, str) else request_data or {}

	# Ensure items list exists
	if not isinstance(data.get("items"), list):
		data["items"] = []
	# ---  Company context ---
	company_name = (
		data.get("company_name")
		or frappe.defaults.get_user_default("Company")
		or frappe.get_value("Company", {}, "name")
	)

	# -- Ensure supplier exists ---
	supplier_name = get_or_create_supplier_from_smart(data)

	# --- Find existing PI (Smart linked) ---
	smart_purchase_id = data.get("purchase_id")
	#  If no unique Smart ID provided, generate one dynamically using supplier + date + random hash
	#  If no unique Smart ID provided, generate one dynamically using supplier + date + random hash
	if not smart_purchase_id:
		smart_purchase_id = (
			f"{data.get('supplier_tpin')}-{data.get('invoice_date')}-{frappe.generate_hash('', 6)}"
		)

	# frappe.throw(str(data))
	existing_pi_name = frappe.db.get_value(
		"Purchase Invoice",
		{"custom_smart_purchase_id": smart_purchase_id},
		"name",
	)

	pi = None

	if existing_pi_name:
		pi = frappe.get_doc("Purchase Invoice", existing_pi_name)

		if pi.docstatus == 1:
			#  Already submitted — don’t modify it
			frappe.msgprint(
				f"Purchase Invoice {pi.name} already submitted for supplier {pi.supplier}. Skipping recreation."
			)
			return

		elif pi.docstatus == 2:
			#  Cancelled — create a new one
			frappe.log_error(
				f"Smart Purchase {smart_purchase_id} linked to cancelled PI {pi.name}. Creating new one.",
				"ZRA Smart Purchase",
			)
			pi = frappe.new_doc("Purchase Invoice")
			pi.custom_smart_purchase_id = smart_purchase_id

		else:
			# Draft but editable
			pi.reload()
			pi.set("items", [])

	else:
		#  Create new invoice
		pi = frappe.new_doc("Purchase Invoice")
		pi.custom_smart_purchase_id = smart_purchase_id
		smart_doc_name = frappe.db.get_value(
    "Crystallised ZRA Smart Purchases",
    {"purchase_id": smart_purchase_id},
    "name",
)

	
		if "currency" in data:
			# The "currency" key is only available when creating from Imported Item
			pi.currency = data["currency"]
			# pi.custom_source_registered_imported_item = data["name"]
		else:
			if smart_doc_name:
				pi.custom_source_registered_purchase = smart_doc_name


	# --- Basic fields ---
	pi.company = company_name
	pi.supplier = supplier_name
	pi.currency = data.get("currency", "ZMW")
	pi.bill_no = data.get("invoice_no") or data.get("spplrInvcNo")
	pi.bill_date = data.get("invoice_date") or data.get("salesDt") or today()
	pi.posting_date = today()
	pi.update_stock = 1
	pi.buying_price_list = frappe.db.get_value("Buying Settings", None, "price_list") or "Standard Buying"

	# --- Warehouse ---
	branch_name = data.get("branch") or data.get("branch_id")
	set_warehouse = None

	if branch_name:
		set_warehouse = frappe.db.get_value(
			"Warehouse",
			{
				"company": company_name,
				"warehouse_name": ["like", f"%{branch_name}%"],
				"is_group": 0,
			},
			"name",
		)

	if not set_warehouse:
		set_warehouse = (
			frappe.db.get_value("Warehouse", {"company": company_name, "is_group": 0}, "name")
			or "Main Warehouse"
		)

	pi.set_warehouse = set_warehouse
	pi.custom_smart_branch = branch_name
	pi.custom_smart_organisation = data.get("organisation")
	

	# --- Expense account ---
	company_abbr = frappe.get_value("Company", company_name, "abbr")
	expense_account = (
		frappe.db.get_value(
			"Account",
			{"company": company_name, "root_type": "Expense", "is_group": 0},
			"name",
		)
		or f"Cost of Goods Sold - {company_abbr}"
	)

	# ---  Smart items ---
	for item in data.get("items", []):
		item_code = get_or_create_item_from_smart(item)
		qty = flt(item.get("qty") or item.get("quantity") or 1)
		rate = flt(item.get("prc") or item.get("unit_price") or 0.0)
		amount = qty * rate
		uom = item.get("qtyUnitCd") or item.get("quantity_unit_code") or "Nos"

		pi.append(
			"items",
			{
				"item_code": item_code,
				"item_name": item.get("itemNm") or item.get("item_name"),
				"qty": qty,
				"rate": rate,
				"amount": amount,
				"uom": uom,
				"stock_uom": uom,
				"conversion_factor": 1.0,
				"warehouse": set_warehouse,
				"expense_account": expense_account,
				"custom_smart_packaging_unit": item.get("packaging_unit_code"),
				"custom_smart_item_classification_code": item.get("item_class_code"),
				"custom_smart_vat_category": item.get("vat_category_code"),
				"custom_smart_quantity_unit": item.get("quantity_unit_code"),
			},
		)

	# ---  Safe save & submit ---
	pi.flags.ignore_permissions = True
	pi.flags.ignore_mandatory = True
	pi.flags.ignore_links = True

	pi.run_method("set_missing_values")
	pi.run_method("calculate_taxes_and_totals")

	pi.save(ignore_permissions=True)

	try:
		if pi.docstatus == 0:
			pi.submit()
	except frappe.ValidationError:
		frappe.log_error(frappe.get_traceback(), f"Smart Purchase Invoice Submit Error ({pi.name})")

	frappe.msgprint(f" Purchase Invoice '{pi.name}' created or updated for supplier {supplier_name}.")


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

	frappe.msgprint(f" Created or linked {len(created_items)} Smart items.")


def submit_smart_purchase_invoice(doc: Document) -> None:
	"""
	Submit a Purchase Invoice or Debit Note to the Smart Invoice System (ZRA).
	Handles multi-company setups and prevents duplicate submissions.
	"""

	# Ensure we have a proper Document object
	if isinstance(doc, str):
		# frappe.throw(str(doc))
		doc = frappe.get_doc("Purchase Invoice", doc)

	# Skip if already submitted to Smart
	if getattr(doc, "custom_smart_invoice_number", None):
		frappe.log_error(f"Invoice {doc.name} already has a Smart Invoice Number — skipping submission.")
		return

	company_name = doc.company
	active_settings = get_active_smart_settings()

	# Find settings for this company
	company_setting = next((s for s in active_settings if s.get("company") == company_name), None)

	if not company_setting:
		frappe.log_error(f"No Smart settings found for company: {company_name}", "Smart Submission Error")
		return

	# Skip if Smart submission is explicitly disabled
	if getattr(doc, "prevent_smart_submission", False):
		frappe.msgprint("Smart submission prevented for this document.")
		return

	try:
		route_key = "savePurchase"
		payload = build_purchase_payload(doc.name, company_setting.get("name"))
		success_message = "Smart Purchase Invoice submission queued successfully."

		# Process API request
		process_request(
			request_data=payload,
			route_key=route_key,
			handler_function=lambda response, **_: purchase_invoice_submission_on_success(
				response=response,
				document_name=doc.name,
				doctype="Purchase Invoice",
				settings_name=company_setting["name"],
			),
			request_method="POST",
			doctype="Purchase Invoice",
			document_name=doc.name,
			settings_name=company_setting["name"],
		)

		frappe.msgprint(success_message)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Smart Purchase/Debit Note Submission Failed")
		frappe.throw(f"Error submitting to Smart: {e}")


def on_error(error):
	"""Generic error logger for Smart API failures."""
	frappe.log_error(
		title="VSDC API Error",
		message=f"Failed to submit document to VSDC: {error}",
	)


@frappe.whitelist()
def send_purchase_details(doc, method=None) -> None:
	"""
	Manually trigger Smart submission for a Purchase Invoice or Debit Note.
	"""
	submit_smart_purchase_invoice(doc)

@frappe.whitelist()
def perform_purchases_search(company: str) -> None:
    """
    Fetch purchases from ZRA Smart Invoice System for a given company.
    """
    # Get active Smart settings for the company
    settings = get_settings(company)
    if not settings:
        frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings found for {company}")
        return

    # Decrypt TPIN from Smart settings
    tpin = settings.tpin

    # Default branch ID
    bhf_id = settings.get("bhfid") or "000"

    # Default request date (1 year back)
    request_date = add_to_date(datetime.now(), years=-1).strftime("%Y%m%d%H%M%S")

    # Fetch the last_request_date saved for this route
    _, last_req_date = get_route_path("selectTrnsPurchaseSales", "Crystal VSDC")
    if last_req_date:
        last_req_dt = last_req_date.strftime("%Y%m%d%H%M%S")
    else:
        last_req_dt = request_date

    # Prepare request payload (required by ZRA API)
    request_data = {
        "Tpin": tpin,
        "BhfId": bhf_id,
        "LastReqDt": last_req_dt,
    }

    try:
        process_request(
            request_data=request_data,
            route_key="selectTrnsPurchaseSales",
            handler_function=purchase_search_on_success,
            request_method="POST",
            doctype=REGISTERED_PURCHASES_DOCTYPE_NAME,
        )

        frappe.msgprint("Smart purchase fetch request sent successfully.")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Smart Purchase Fetch Failed")
        frappe.throw(f"Error fetching purchases from ZRA: {e}")


@frappe.whitelist()
def create_supplier_from_smart_purchase(request_data: str) -> None:
	"""
	Creates a Supplier from ZRA Smart Purchase data.
	Can be called from a Frappe client (JS) or internal function.
	"""
	if isinstance(request_data, str):
		data = json.loads(request_data)
	else:
		data = request_data

	supplier_doc = get_or_create_supplier_from_smart(data)

	frappe.msgprint(f"Supplier <b>{supplier_doc}</b> successfully created or linked.")
