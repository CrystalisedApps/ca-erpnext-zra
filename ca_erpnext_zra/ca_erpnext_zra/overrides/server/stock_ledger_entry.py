import re
from decimal import ROUND_DOWN, Decimal
from functools import partial
from typing import Literal
from frappe.utils import getdate
import frappe
from erpnext.controllers.taxes_and_totals import get_itemised_tax_breakup_data
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password

from ...apis.api_processor import process_request
from ...handlers.error_handler import handle_errors
from ...utils.settings_utils import get_settings
from ...utils.smart_api_utils import split_user_email


def on_update(doc: Document, method: str | None = None) -> None:
	"""Handle stock movements and submit to ZRA Smart Invoice via process_request."""

	company_name = doc.company
	vendor = ""
	
	all_items = frappe.db.get_all("Item", ["*"])  # Get all items for details
	record = frappe.get_doc(doc.voucher_type, doc.voucher_no)
	series_no = sar_no = int(re.sub(r"\D", "", doc.name)[-5:]) or 1
	company = doc.company
	settings = get_settings(company)
	if not settings:
		frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings for {company}")
		return

	tpin = settings.tpin

	# Base payload
	payload = {
		"tpin": tpin,
		"bhfId": "000",
		"sarNo": series_no,
		"orgSarNo": series_no,
		"regTyCd": "M",
		"custTin": None,
		"custNm": None,
		"custBhfId": None,
		"ocrnDt": record.posting_date.strftime("%Y%m%d"),
		"totTaxblAmt": 0,
		"totItemCnt": len(record.items),
		"totTaxAmt": 0,
		"totAmt": 0,
		"remark": None,
		"regrId": split_user_email(record.owner),
		"regrNm": record.owner,
		"modrNm": record.modified_by,
		"modrId": split_user_email(record.modified_by),
	}

	# Determine the correct SAR type and items payload based on voucher type
	if doc.voucher_type == "Stock Reconciliation":
		items_list = get_stock_recon_movement_items_details(record.items, all_items)
		current_item = [i for i in items_list if i["itemNm"] == doc.item_code]
		qty_diff = int(current_item[0].pop("quantity_difference"))
		payload["itemList"] = current_item
		payload["totItemCnt"] = len(current_item)
		payload["sarTyCd"] = "06" if record.purpose == "Opening Stock" else ("16" if qty_diff < 0 else "06")

	elif doc.voucher_type == "Stock Entry":
		items_list = get_stock_entry_movement_items_details(record.items, all_items)
		current_item = [i for i in items_list if i["itemNm"] == doc.item_code]
		payload["itemList"] = current_item
		payload["totItemCnt"] = len(current_item)

		# Map stock entry types to SAR codes
		sar_map = {
			"Material Receipt": "04",
			"Material Transfer": "13" if doc.actual_qty < 0 else "04",
			"Manufacture": "05" if doc.actual_qty > 0 else "14",
			"Send to Subcontractor": "13",
			"Material Issue": "13",
			"Repack": "05" if doc.actual_qty > 0 else "14",
		}
		payload["sarTyCd"] = sar_map.get(record.stock_entry_type, "06")

	elif doc.voucher_type in ("Purchase Receipt", "Purchase Invoice"):
		items_list = get_purchase_docs_items_details(record.items, all_items)
		item_taxes = get_itemised_tax_breakup_data(record)
		current_item = [i for i in items_list if i["itemNm"] == doc.item_code]
		payload["itemList"] = current_item
		payload["totItemCnt"] = len(current_item)

		if record.is_return:
			payload["sarTyCd"] = "12"
		else:
			payload["sarTyCd"] = "01" if current_item[0]["is_imported_item"] else "02"

	elif doc.voucher_type in ("Delivery Note", "Sales Invoice"):
		if doc.voucher_type == "Sales Invoice" and record.custom_successfully_submitted != 1:
			return

		items_list = get_notes_docs_items_details(record.items, all_items)
		item_taxes = get_itemised_tax_breakup_data(record)
		current_item = [i for i in items_list if i["itemNm"] == doc.item_code]
		payload["itemList"] = current_item
		payload["totItemCnt"] = len(current_item)
		payload["custNm"] = record.customer
		payload["custTin"] = record.tax_id
		payload["sarTyCd"] = "03" if record.is_return and doc.actual_qty > 0 else "11"

	# Build final request

	job_name = frappe.generate_hash(length=16)

	# Submit asynchronously using process_request
	process_request(
		route_key="saveStockItems",
		request_data=payload,
		handler_function=partial(stock_mvt_submission_on_success, document_name=doc.name),
		error_callback=on_error,
		request_method="POST",
		doctype="Stock Ledger Entry",
		document_name=doc.name,
	)


# def get_warehouse_branch_id(warehouse_name: str) -> str | Literal[0]:
#     branch_id = frappe.db.get_value(
#         "Warehouse", {"name": warehouse_name}, ["custom_branch"], as_dict=True
#     )

#     if branch_id:
#         return branch_id.custom_branch

#     return


def get_stock_entry_movement_items_details(records: list[Document], all_items: list[Document]) -> list[dict]:
	items_list = []

	for item in records:
		for fetched_item in all_items:
			if item.item_code == fetched_item.name:
				items_list.append(
					{
						"itemSeq": item.idx,
						"itemCd": fetched_item.custom_smart_item_code,
						"itemClsCd": fetched_item.custom_smart_item_classification_code,
						"itemNm": fetched_item.item_code,
						"bcd": None,
						"pkgUnitCd": fetched_item.custom_smart_packaging_unit,
						"pkg": 1,
						"qtyUnitCd": fetched_item.custom_smart_quantity_unit,
						"qty": abs(item.qty),
						"prc": (round(int(item.basic_rate), 2) if item.basic_rate else 0),
						"splyAmt": (round(int(item.basic_rate), 2) if item.basic_rate else 0),
						# TODO: Handle discounts properly
						"totDcAmt": 0,
						"vatCatCd": fetched_item.custom_vat_category_code,
						"taxblAmt": 0,
						"taxAmt": 0,
						"totAmt": 0,
					}
				)

	return items_list


def get_purchase_docs_items_details(items: list, all_present_items: list[Document]) -> list[dict]:
	items_list = []

	for item in items:
		for fetched_item in all_present_items:
			if item.item_code == fetched_item.name:
				items_list.append(
					{
						"itemSeq": item.idx,
						"itemCd": fetched_item.custom_smart_item_code,
						"itemClsCd": fetched_item.custom_smart_item_classification_code,
						"itemNm": fetched_item.item_code,
						"bcd": None,
						"pkgUnitCd": fetched_item.custom_smart_packaging_unit,
						"pkg": 1,
						"qtyUnitCd": fetched_item.custom_smart_quantity_unit,
						"qty": abs(item.qty),
						"prc": (round(int(item.valuation_rate), 2) if item.valuation_rate else 0),
						"splyAmt": (round(int(item.valuation_rate), 2) if item.valuation_rate else 0),
						"totDcAmt": 0,
						"taxblAmt": 0,
						"taxAmt": 0,
						"totAmt": 0,
						"vatCatCd": fetched_item.custom_vat_category_code,
						# "vatCatCd": fetched_item.custom_vat_category_code,
						# "taxblAmt": quantize_number(item.net_amount),
						# "taxAmt": quantize_number(item.custom_tax_amount) or 0,
						# "totAmt": quantize_number(item.net_amount + item.custom_tax_amount),
						"is_imported_item": (
							True
							if (
								fetched_item.custom_imported_item_status
								and fetched_item.custom_imported_item_task_code
							)
							else False
						),
					}
				)

	return items_list


def get_notes_docs_items_details(items: list[Document], all_present_items: list[Document]) -> list[dict]:
	items_list = []

	for item in items:
		for fetched_item in all_present_items:
			if item.item_code == fetched_item.name:
				items_list.append(
					{
						"itemSeq": item.idx,
						"itemCd": fetched_item.custom_smart_item_code,
						"itemClsCd": fetched_item.custom_smart_item_classification_code,
						"itemNm": fetched_item.item_code,
						"bcd": None,
						"pkgUnitCd": fetched_item.custom_smart_packaging_unit,
						"pkg": 1,
						"qtyUnitCd": fetched_item.custom_smart_quantity_unit,
						"qty": abs(item.qty),
						"prc": (round(int(item.base_net_rate), 2) if item.base_net_rate else 0),
						"splyAmt": (round(int(item.base_net_rate), 2) if item.base_net_rate else 0),
						"totDcAmt": 0,
						"vatCatCd": fetched_item.custom_vat_category_code,
						"taxblAmt": 0,
						"taxAmt": 0,
						"totAmt": 0,
						# "taxblAmt": quantize_number(item.net_amount),
						# "taxAmt": quantize_number(item.custom_tax_amount) or 0,
						# "totAmt": quantize_number(item.net_amount + item.custom_tax_amount),
					}
				)

	return items_list


def stock_mvt_submission_on_success(response: dict, document_name: str, **kwargs) -> None:
	frappe.db.set_value("Stock Ledger Entry", document_name, {"custom_submitted_successfully": 1})

def on_error(
    response: dict | str,
    url: str | None = None,
    doctype: str | None = None,
    document_name: str | None = None,
    **kwargs,
) -> None:
    """Base 'on-error' callback with custom_submission_tries tracking."""

    if doctype and document_name:
        try:
            # Fetch current counter directly from DB
            current_tries = frappe.db.get_value(doctype, document_name, "custom_submission_tries") or 0
            # Increment counter
            frappe.db.set_value(doctype, document_name, "custom_submission_tries", current_tries + 1)
            frappe.db.commit()
        except Exception:
            frappe.log_error(
                title=f"Failed to increment custom_submission_tries for {doctype} {document_name}",
                message=frappe.get_traceback()
            )

    # Log the error after updating counter
    handle_errors(
        response,
        route=url,
        doctype=doctype,
        document_name=document_name,
    )


   

def get_stock_recon_movement_items_details(records: list, all_items: list) -> list[dict]:
	items_list = []
	# current_qty

	for item in records:
		for fetched_item in all_items:
			if item.item_code == fetched_item.name:
				items_list.append(
					{
						"itemSeq": item.idx,
						"itemCd": fetched_item.custom_smart_item_code,
						"itemClsCd": fetched_item.custom_smart_item_classification_code,
						"itemNm": fetched_item.item_code,
						"bcd": None,
						"pkgUnitCd": fetched_item.custom_smart_packaging_unit,
						"pkg": 1,
						"qtyUnitCd": fetched_item.custom_smart_quantity_unit,
						"qty": abs(int(item.quantity_difference)),
						"itemExprDt": "",
						"prc": (round(int(item.valuation_rate), 2) if item.valuation_rate else 0),
						"splyAmt": (round(int(item.valuation_rate), 2) if item.valuation_rate else 0),
						"totDcAmt": 0,
						"vatCatCd": fetched_item.custom_vat_category_code,
						"taxblAmt": 0,
						"taxAmt": 0,
						"totAmt": 0,
						"quantity_difference": item.quantity_difference,
					}
				)

	return items_list


def quantize_number(number: str | int | float) -> str:
	"""Return number value to two decimal points"""
	return Decimal(number).quantize(Decimal(".01"), rounding=ROUND_DOWN).to_eng_string()
