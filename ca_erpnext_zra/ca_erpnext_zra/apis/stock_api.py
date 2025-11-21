import json
from functools import partial

import frappe
from frappe.utils import nowdate
from frappe.utils.password import get_decrypted_password

from ..apis.api_processor import process_request
from ..handlers.error_handler import handle_errors
from ..utils.payload_utils import build_sales_payload, build_stock_item_payload, build_stock_payload
from ..utils.settings_utils import get_settings
from ..utils.smart_api_utils import get_active_smart_settings, split_user_email
from .api_processor import process_request


@frappe.whitelist()
def submit_inventory(data, method=None):
	"""
	Enqueue residual quantity submission to ZRA Smart Invoice
	when a Stock Ledger Entry is updated/submitted.
	"""
	# If data arrives as a JSON string, convert it to dict
	if isinstance(data, str):
		try:
			data = json.loads(data)
		except Exception:
			frappe.throw("Invalid JSON payload for submit_inventory")
	# Get active Smart Invoice settings
	settings = _get_single_smart_settings()
	if not settings:
		frappe.log_error("ZRA Settings Missing", "No active Smart Invoice settings found")
		return

	# Decrypt TPIN
	tpin = (
		get_decrypted_password(
			"Crystal ZRA Smart Invoice Settings", settings["name"], "tpin", raise_exception=False
		)
		or ""
	)

	branch_id = getattr(settings, "branch_id", "000") or "000"

	# Build payload
	payload = {
		"tpin": tpin,
		"bhfId": branch_id,
		"regrId": split_user_email(data["owner"]),
		"regrNm": data["owner"],
		"modrId": split_user_email(data["owner"]),
		"modrNm": data["owner"],
		"stockItemList": [
			{
				"itemCd": data["smart_item_code"],  # ZRA smart code
				"rsdQty": data["residual_qty"],
			}
		],
	}

	# Success callback
	success_handler = partial(submit_inventory_on_success, document_name=data["name"])

	# Enqueue async job
	frappe.enqueue(
		process_request,
		queue="default",
		is_async=True,
		request_data=payload,
		route_key="saveStockMaster",  # or the correct endpoint for ZRA
		handler_function=success_handler,
		request_method="POST",
		doctype="Stock Ledger Entry",
		document_name=data["name"],
		error_callback=inventory_error_handler,
	)


def _get_single_smart_settings():
	"""Return single active Smart API settings, or None"""
	settings = get_active_smart_settings()
	return settings[0] if settings else None


def submit_inventory_on_success(response, document_name, **kwargs):
	"""Mark Stock Ledger Entry as successfully submitted"""
	frappe.db.set_value("Stock Ledger Entry", document_name, "custom_inventory_submitted_successfully", 1)


def inventory_error_handler(
	response: dict | str,
	url: str | None = None,
	doctype: str | None = None,
	document_name: str | None = None,
	**kwargs,
):
	handle_errors(
		response,
		route=url,
		doctype=doctype,
		document_name=document_name,
	)


# @frappe.whitelist()
# def send_stock_item_to_zra(doc, method):
#     payload = build_stock_item_payload(doc)
#     process_request(
#         request_data=payload,
#         route_key="saveStockItems",
#         request_method="POST",
#         doctype=doc.doctype,
#         document_name=doc.name,
#     )


# @frappe.whitelist()
# def send_sales_to_zra(doc, method):
#     try:
#         company_name = doc.company

#         settings = get_settings()
#         tpin = get_decrypted_password(
#             "Crystal ZRA Smart Invoice Settings",
#             settings.name,
#             "tpin",               # fieldname
#             raise_exception=False
#         ) or ""
#         if not settings:
#             frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings for {company_name}")
#             return

#         payload = build_sales_payload(doc.name, company_tpin=tpin, user=frappe.session.user)

#         process_request(
#             request_data=payload,
#             route_key="saveStockItems",
#             request_method="POST",
#             doctype="Sales Invoice",
#             document_name=doc.name,
#         )

#         frappe.logger().info(f"✅ Successfully queued sales submission for {doc.name}")

#        # --- Enqueue async stock sync job ---
#         frappe.enqueue(
#             "ca_erpnext_zra.ca_erpnext_zra.apis.stock_api.sync_stock_to_zra",
#             queue="long",
#             company_name=company_name,
#             tpin=tpin,

#             now=False  # async
#         )

#         frappe.logger().info(f"🧭 Enqueued stock sync job for {company_name}")

#     except Exception:
#         frappe.log_error(
#             title="ZRA Sales Submission Error",
#             message=f"Error processing {doc.name} for {company_name}:\n{frappe.get_traceback()}",
#         )


# @frappe.whitelist()
# def sync_stock_from_sle(doc, method=None):
#     """Triggered from Stock Ledger Entry — sync stock movement to ZRA Smart Invoice."""
#     try:
#         company = doc.company
#         settings = get_settings(company)
#         if not settings:
#             frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings for {company}")
#             return

#         tpin = get_decrypted_password(
#             "Crystal ZRA Smart Invoice Settings",
#             settings.name,
#             "tpin",
#             raise_exception=False
#         ) or ""

#         bhf_id = settings.get("bhfid") or "000"
#         user = frappe.session.user or "Admin"

#         # Choose the correct route
#         if doc.actual_qty > 0:
#             route_key = "saveStockItems"     # incoming stock → SaveStockItems
#         elif doc.actual_qty < 0:
#             route_key = "SaveStockMaster"    # outgoing or adjustment → SaveStockMaster
#         else:
#             frappe.logger().info(f"⚠️ Skipping zero-qty SLE {doc.name}")
#             return

#         # Build full item data (esp. for SaveStockItems)
#         stock_item = {
#             "itemCd": doc.item_code,
#             "qty": abs(doc.actual_qty),
#             "rsdQty": abs(doc.actual_qty),
#             "prc": frappe.db.get_value("Item", doc.item_code, "valuation_rate") or 100,
#             "itemNm": frappe.db.get_value("Item", doc.item_code, "item_name"),
#         }

#         # Prepare payload
#         stock_payload = build_stock_payload(
#             tpin=tpin,
#             bhf_id=bhf_id,
#             user=user,
#             stock_items=[stock_item],
#             route_key=route_key,
#         )

#         # Enqueue async call
#         frappe.enqueue(
#             "ca_erpnext_zra.ca_erpnext_zra.apis.api_processor.process_request",
#             queue="long",
#             request_data=stock_payload,
#             route_key=route_key,
#             request_method="POST",
#             doctype="Stock Ledger Entry",
#             document_name=doc.name,
#             now=False,
#         )

#         frappe.logger().info(f"📦 Enqueued ZRA sync for SLE {doc.name} ({route_key})")

#     except Exception:
#         frappe.log_error(
#             title="ZRA SLE Sync Error",
#             message=f"Error syncing SLE {doc.name}:\n{frappe.get_traceback()}",
#         )
