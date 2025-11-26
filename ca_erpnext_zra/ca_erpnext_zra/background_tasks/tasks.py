import json
from functools import partial

import frappe
from frappe.model.document import Document
from ..utils.smart_api_utils import get_max_submission_attempts
from ..apis.api_processor import process_request
from ..apis.stock_api import submit_inventory
from ..handlers.error_handler import handle_errors
from ..overrides.server.stock_ledger_entry import on_update
from ..services.code_list_service import sync_item_codes, sync_vsdc_codes


@frappe.whitelist()
def refresh_vsdc_codes(settings_name: str, last_req_dt: str = None) -> dict:
	"""
	Fetch and update all code lists (currencies, packaging units, taxation, etc.)
	from Crystal VSDC using the SelectCodes endpoint.
	"""
	return sync_vsdc_codes(settings_name=settings_name, last_req_dt=last_req_dt)


def send_item_inventory_information(*args, **kwargs) -> None:
	"""Submit residual (closing) inventory quantities to ZRA Smart Invoice."""
	frappe.logger().info("[SMART] Scheduler fired: send_item_inventory_information")
	# Fetch all SLE records where movement was submitted but inventory not yet submitted
	query = """
            SELECT
            sle.name AS name,
            sle.owner,
            sle.custom_inventory_submitted_successfully,
            sle.qty_after_transaction AS residual_qty,
			sle.custom_submission_tries,
			sle.company,
            sle.warehouse,
            "000" AS branch_id,
            i.item_code AS item_code,                     -- ✔ correct: true ERPNext item code
            i.custom_smart_item_code AS smart_item_code   -- ✔ renamed to avoid overwriting item_code
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` i ON sle.item_code = i.item_code
        WHERE sle.custom_submitted_successfully = 1
        AND sle.custom_inventory_submitted_successfully = 0
        ORDER BY sle.creation DESC

    """

	sles = frappe.db.sql(query, as_dict=True)
	# frappe.throw(str(sles))
	if not sles:
		return

	for sle in sles:
		response = json.dumps(sle)
		max_tries = get_max_submission_attempts("Stock Ledger Entry", company=sle.company)
		if sle.custom_submission_tries and int(sle.custom_submission_tries) >= max_tries:
			return

		try:
			submit_inventory(response)

		except Exception as error:
			# TODO: Suspicious looking type(error)
			frappe.log_error(f"Inventory Sync Failed: {error}")


def send_stock_information(*args, **kwargs) -> None:
	all_stock_ledger_entries: list[Document] = frappe.get_all(
		"Stock Ledger Entry",
		{"docstatus": 1, "custom_submitted_successfully": 0},
		["name"],
	)
	for entry in all_stock_ledger_entries:
		doc = frappe.get_doc("Stock Ledger Entry", entry.name, for_update=False)
		max_tries = get_max_submission_attempts("Stock Ledger Entry", company=doc.company)
		if doc.custom_submission_tries and int(doc.custom_submission_tries) >= max_tries:
			return
		try:
			on_update(doc, method=None)

		except TypeError:
			continue


@frappe.whitelist()
def get_item_classification_codes(settings_name: str, LastReqDt: str = None) -> str:
	"""Fetch item classification codes  from ZRA VSDC."""
	return sync_item_codes(settings_name=settings_name, LastReqDt=LastReqDt)
