import re

# from .id_utils import get_vsdc_id

from typing import Any, Callable, Dict
from datetime import datetime

import frappe
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_datetime, getdate, now, now_datetime
from frappe.utils.password import get_decrypted_password
from ..utils.settings_utils import get_settings
from .tax_utils import calculate_tax


def map_zra_purchase_to_payload(purchase_data: dict, company_tpin: str) -> dict:
	sale_items = purchase_data.get("itemList", [])
	payload = {
		"tpin": company_tpin,
		"bhfId": "000",
		"cisInvcNo": f"cis{purchase_data.get('spplrInvcNo')}",
		"orgInvcNo": 0,
		"spplrTpin": purchase_data.get("spplrTpin"),
		"spplrBhfId": purchase_data.get("spplrBhfId", "000"),
		"spplrNm": purchase_data.get("spplrNm"),
		"spplrInvcNo": str(purchase_data.get("spplrInvcNo")),
		"regTyCd": "M",
		"pchsTyCd": "N",
		"rcptTyCd": "P",
		"pmtTyCd": purchase_data.get("pmtTyCd", "01"),
		"pchsSttsCd": "02",
		"cfmDt": datetime.now().strftime("%Y%m%d%H%M%S"),
		"pchsDt": purchase_data.get("salesDt"),
		"cnclReqDt": "",
		"cnclDt": "",
		"totItemCnt": purchase_data.get("totItemCnt", len(sale_items)),
		"totTaxblAmt": purchase_data.get("totTaxblAmt"),
		"totTaxAmt": purchase_data.get("totTaxAmt"),
		"totAmt": purchase_data.get("totAmt"),
		"remark": purchase_data.get("remark", ""),
		"regrNm": frappe.session.user or "ADMIN",
		"regrId": frappe.session.user or "ADMIN",
		"modrNm": frappe.session.user or "ADMIN",
		"modrId": frappe.session.user or "ADMIN",
		"itemList": [],
	}

	for item in sale_items:
		payload["itemList"].append(
			{
				"itemSeq": item.get("itemSeq"),
				"itemCd": item.get("itemCd"),
				"itemClsCd": item.get("itemClsCd"),
				"itemNm": item.get("itemNm"),
				"bcd": item.get("bcd"),
				"pkgUnitCd": item.get("pkgUnitCd", "EA"),
				"pkg": item.get("pkg", 0),
				"qtyUnitCd": item.get("qtyUnitCd", "EACH"),
				"qty": item.get("qty", 1),
				"prc": item.get("prc"),
				"splyAmt": item.get("splyAmt"),
				"dcRt": item.get("dcRt", 0),
				"dcAmt": item.get("dcAmt", 0),
				"taxTyCd": item.get("vatCatCd", "A"),
				"vatCatCd": item.get("vatCatCd", "A"),
				"taxblAmt": item.get("taxblAmt"),
				"taxAmt": item.get("vatAmt", 0),
				"totAmt": item.get("totAmt"),
				"iplCatCd": None,
				"tlCatCd": None,
				"exciseCatCd": None,
				"iplTaxblAmt": None,
				"tlTaxblAmt": None,
				"exciseTaxblAmt": None,
				"iplAmt": None,
				"tlAmt": None,
				"exciseTxAmt": None,
			}
		)

	return payload


def _safe_float(value) -> float:
	return flt(value)


def _fmt_datetime(date_time_str) -> str:
	if date_time_str:
		try:
			dt_obj = get_datetime(date_time_str)
			return dt_obj.strftime("%Y%m%d%H%M%S")
		except Exception:
			return ""
	return ""


def _fmt_date(date_str) -> str:
	if date_str:
		try:
			d_obj = getdate(date_str)
			return d_obj.strftime("%Y%m%d")
		except Exception:
			return ""
	return ""


def build_debit_note_payload(docname: str, settings_name: str | None = None) -> dict[str, Any]:
	"""
	Build a Debit Note payload for Smart Invoice (ZRA) from a Sales Invoice.

	This is used when:
	 - Undercharged customer
	 - Wrong qty
	 - Wrong price
	 - Omitted items
	 - Customer Debit Note required

	"""

	# ------------------
	# 1. Fetch Sales Invoice and Settings
	# ------------------
	doc = frappe.get_doc("Sales Invoice", docname)

	tpin = ""
	branch_code = "000"
	try:
		if hasattr(doc, "branch") and doc.branch:
			branch_doc = frappe.get_doc("Branch", doc.branch)
			branch_code = branch_doc.get("custom_branch_code") or "000"
	except Exception as e:
		frappe.log_error(f"Failed to fetch branch code: {e}", "Branch Code Error")

	if not settings_name:
		settings_record = frappe.get_all("Crystal ZRA Smart Invoice Settings", fields=["name"], limit=1)
		if settings_record:
			settings_name = settings_record[0]["name"]

	if settings_name:
		settings = get_settings(settings_name)
		tpin = settings.get("tpin")

	user = frappe.session.user or "admin"

	# ------------------
	# Dates
	# ------------------
	cfm_dt = _fmt_datetime(doc.posting_date)
	sales_dt = _fmt_date(doc.posting_date)

	# ------------------
	# CUSTOMER FIELDS (SALES, NOT PURCHASE)
	# ------------------
	cust_tpin_val = cstr(getattr(doc, "customer_tpin", None))
	safe_cust_tpin = cust_tpin_val if cust_tpin_val else None

	customer_name = doc.customer_name or doc.customer

	lpo_number_val = cstr(getattr(doc, "lpo_number", None))
	safe_lpo_number = lpo_number_val if (lpo_number_val and 9 <= len(lpo_number_val) <= 20) else None

	# ------------------
	# ORIGINAL ZRA INVOICE NUMBER (MANDATORY)
	# ------------------
	original_zra_slip = cstr(doc.get("original_invoice_number") or "")
	return_against = cstr(doc.get("return_against") or "")
	custom_original = cstr(doc.get("custom_sdc_invoice_number") or "")

	org_invc_no_val = None

	if original_zra_slip:
		org_invc_no_val = original_zra_slip
	elif return_against:
		org_invc_no_val = return_against
	elif custom_original:
		org_invc_no_val = custom_original

	# Extract last numeric segment if it looks like: SI-INV-2025-00492
	extracted_numeric_suffix = None
	if org_invc_no_val:
		try:
			parts = org_invc_no_val.split("-")
			numeric_part = parts[-1]
			extracted_numeric_suffix = cstr(int(numeric_part))
		except Exception:
			extracted_numeric_suffix = org_invc_no_val

	safe_org_invc_no = (
		extracted_numeric_suffix if extracted_numeric_suffix and extracted_numeric_suffix != "0" else None
	)

	# ------------------
	# Load VAT Rates
	# ------------------
	rates = {
		"A": 16,
		"B": 16,
		"C1": 0,
		"C2": 0,
		"C3": 0,
		"D": 0,
		"Rvat": 16,
		"E": 0,
		"F": 10,
		"Ipl1": 5,
		"Ipl2": 0,
		"Tl": 1.5,
		"Ecm": 5,
		"Exeeg": 3,
		"Tot": 0,
	}

	# ------------------
	# BASE PAYLOAD (SALES VERSION)
	# ------------------
	payload = {
		"tpin": tpin,
		"bhfId": branch_code or "000",
		"cisInvcNo": cstr(doc.get("custom_cis_number") or doc.name),
		# SALES — correct mapping
		"custTpin": safe_cust_tpin,
		"custNm": customer_name,
		"salesTyCd": "N",
		"rcptTyCd": "D",  # DEBIT NOTE
		"pmtTyCd": cstr(doc.get("payment_type_code") or "01"),
		"salesSttsCd": "02",
		"cfmDt": cfm_dt,
		"salesDt": sales_dt,
		"stockRlsDt": None,
		"cnclReqDt": None,
		"cnclDt": None,
		"rfdDt": None,
		"rfdRsnCd": None,
		"totItemCnt": len(doc.items),
		# TAX BUCKETS INIT
		**{f"taxblAmt{k}": 0.0 for k in rates},
		**{f"taxAmt{k}": 0.0 for k in rates},
		**{f"taxRt{k}": rates[k] for k in rates},
		"totTaxblAmt": 0.0,
		"totTaxAmt": 0.0,
		"totAmt": 0.0,
		"tlAmt": 0.0,
		"cashDcRt": _safe_float(doc.get("additional_discount_percentage") or 0),
		"cashDcAmt": _safe_float(doc.get("discount_amount") or 0),
		"prchrAcptcYn": "N",
		"remark": cstr(doc.get("remarks") or ""),
		"regrId": user,
		"regrNm": user,
		"modrId": user,
		"modrNm": user,
		"saleCtyCd": "1",
		"currencyTyCd": doc.currency or "ZMW",
		"exchangeRt": "1",
		"destnCountryCd": "",
		"dbtRsnCd": cstr(doc.get("custom_adjust_reason") or "03"),
		"invcAdjustReason": cstr(doc.get("custom_debit_reason_code") or ""),
		"itemList": [],
	}

	# Conditionally add lpoNumber only if valid (9-20 characters)
	if safe_lpo_number:
		payload["lpoNumber"] = safe_lpo_number

	# only add ON ORIGINAL INVOICE IF EXISTS
	if safe_org_invc_no:
		payload["orgInvcNo"] = safe_org_invc_no

	# ------------------
	# ITEM LOOP (identical to your logic but mapped to Sales Invoice)
	# ------------------
	for idx, itm in enumerate(doc.items, 1):
		item_code = (
			itm.get("custom_smart_item_code")
			or frappe.db.get_value("Item", itm.item_code, "custom_smart_item_code")
			or itm.item_code
		)
		item_name = cstr(itm.item_name)

		item_cls = (
			itm.get("custom_item_classification")
			or frappe.db.get_value("Item", item_code, "custom_smart_item_classification_code")
			or "50102517"
		)
		qty_unit_cd = (
			itm.get("custom_qty_unit_code")
			or frappe.db.get_value("Item", item_code, "custom_smart_quantity_unit")
			or "EA"
		)

		pkg_unit_cd = (
			itm.get("custom_pkg_unit_code")
			or frappe.db.get_value("Item", item_code, "custom_smart_packaging_unit")
			or "EA"
		)
		qty = abs(_safe_float(itm.qty))
		rate = abs(_safe_float(itm.rate))
		dc_amt = abs(_safe_float(itm.discount_amount))
		dc_rt = abs(_safe_float(itm.discount_percentage))

		vat_cat_cd = itm.get("vat_category") or "A"
		tax_rate = rates.get(vat_cat_cd, 0.0)

		# exact ZRA calculations
		sply_amt = round(rate * qty, 2)
		vat_rate = round(rate * tax_rate / 100, 4)  # VAT per unit
		vat_amt = round(sply_amt * tax_rate / 100, 2)  # Total VAT on line
		sply_rate = round(rate + vat_rate, 4)  # Rate including VAT

		tot_amt = round(sply_amt - dc_amt + vat_amt, 2)
		tl_amt = tot_amt
		# accumulate
		payload[f"taxblAmt{vat_cat_cd}"] += sply_amt
		payload[f"taxAmt{vat_cat_cd}"] += vat_amt

		# item payload
		payload["itemList"].append(
			{
				"itemSeq": idx,
				"itemCd": item_code,
				"itemNm": item_name,
				"itemClsCd": item_cls,
				"qty": qty,
				"qtyUnitCd": qty_unit_cd,
				"prc": sply_rate,
				"splyAmt": tl_amt,
				"vatAmt": vat_amt,
				"totAmt": tot_amt,
				"tlAmt": 0,
				"vatTaxblAmt": sply_amt,
				"tlTaxblAmt": sply_amt,
				"dcAmt": dc_amt,
				"dcRt": dc_rt,
				"vatCatCd": vat_cat_cd,
				"bcd": itm.get("barcode") or "",
				"pkg": 1,
				"pkgUnitCd": pkg_unit_cd,
			}
		)

	# ------------------
	# Final totals
	# ------------------
	payload["totTaxblAmt"] = round(sum(payload[f"taxblAmt{k}"] for k in rates), 4)
	payload["totTaxAmt"] = round(sum(payload[f"taxAmt{k}"] for k in rates), 2)
	payload["totAmt"] = round(sum(i["totAmt"] for i in payload["itemList"]) - payload["cashDcAmt"], 2)

	return payload


@frappe.whitelist()
def build_purchase_payload(docname: str, settings_name: str) -> dict:
    # Fetch Purchase Invoice
    doc = frappe.get_doc("Purchase Invoice", docname)
    
    # Get the linked Crystallised ZRA Smart Purchases document
    # Try multiple ways to find the existing document
    crystal_doc = None
    
    # METHOD 1: Try by purchase_id (Purchase Invoice name)
    crystal_name = frappe.db.exists("Crystallised ZRA Smart Purchases", {"purchase_id": docname})
    
    # METHOD 2: Try by supplier invoice number
    if not crystal_name:
        supplier_invoice_no = doc.get("bill_no") or doc.get("supplier_invoice_no")
        if supplier_invoice_no:
            crystal_name = frappe.db.exists(
                "Crystallised ZRA Smart Purchases", 
                {"supplier_invoice_no": supplier_invoice_no}
            )
    
    # METHOD 3: Try by custom_smart_purchase_id (if set on Purchase Invoice)
    if not crystal_name and getattr(doc, "custom_smart_purchase_id", None):
        crystal_name = frappe.db.exists(
            "Crystallised ZRA Smart Purchases", 
            {"purchase_id": doc.custom_smart_purchase_id}
        )
    
    # METHOD 4: Try by supplier name and date range (last resort)
    if not crystal_name:
        # Look for Crystallised documents with same supplier name in last 7 days
        from frappe.utils import add_days, getdate
        
        week_ago = add_days(getdate(), -7)
        possible_docs = frappe.get_all(
            "Crystallised ZRA Smart Purchases",
            filters={
                "supplier_name": doc.supplier_name,
                "sales_date": [">=", week_ago],
                "total_amount": [">", 0]  # Only consider docs with actual values
            },
            fields=["name"],
            order_by="creation desc",
            limit=5
        )
        if possible_docs:
            crystal_name = possible_docs[0].name
    
    if crystal_name:
        crystal_doc = frappe.get_doc("Crystallised ZRA Smart Purchases", crystal_name)
        print(f"Found existing Crystallised document: {crystal_name}")
        print(f"Values from Crystallised doc:")
        print(f"  - total_amount: {crystal_doc.total_amount}")
        print(f"  - total_tax_amount: {crystal_doc.total_tax_amount}")
        print(f"  - total_taxable_amount: {crystal_doc.total_taxable_amount}")
        print(f"  - total_item_count: {crystal_doc.total_item_count}")
    else:
        print("WARNING: No existing Crystallised document found with matching data!")

    # Fetch first settings record
    settings = get_settings(settings_name)
    tpin = ""
    
    if settings:
        tpin = settings.get("tpin")

    # --- Helper: safely get numeric supplier invoice number ---
    def get_supplier_invoice_number(value):
        try:
            # If doc.name ends like "ACC-PINV-2025-00002" → returns 2
            return int(str(value).split("-")[-1])
        except Exception:
            return 0

    # Dynamic codes
    rcpt_ty_cd = "R" if getattr(doc, "is_return", 0) else "P"
    reg_ty_cd = "A" if getattr(doc, "custom_smart_purchase_id", None) else "M"
    branch_code = "000"
    
    try:
        if hasattr(doc, "branch") and doc.branch:
            branch_doc = frappe.get_doc("Branch", doc.branch)
            branch_code = branch_doc.get("custom_branch_code") or "000"
    except Exception as e:
        frappe.log_error(f"Failed to fetch branch code: {e}", "Branch Code Error")

    # USE VALUES FROM EXISTING CRYSTALLISED DOCUMENT IF FOUND
    if crystal_doc:
        # Get totals from Crystallised document
        total_item_count = crystal_doc.total_item_count
        total_taxable_amount = crystal_doc.total_taxable_amount
        total_tax_amount = crystal_doc.total_tax_amount
        total_amount = crystal_doc.total_amount
        
        # Get other fields from Crystallised document
        # IMPORTANT: crystal_doc.supplier_tpin contains supplier NAME, not actual TPIN
        # This is because it's a Link field that stores the linked record name
        # We need to fetch the actual TPIN from the Supplier record
        supplier_name_from_crystal = crystal_doc.supplier_tpin
        actual_supplier_tpin = None
        
        if supplier_name_from_crystal:
            # Fetch the actual TPIN from the Supplier record
            actual_supplier_tpin = frappe.db.get_value("Supplier", supplier_name_from_crystal, "tax_id")
            print(f"DEBUG: Supplier name from crystal: {supplier_name_from_crystal}")
            print(f"DEBUG: Actual TPIN fetched: {actual_supplier_tpin}")
            
            # If no tax_id in supplier record, try to use the supplier name as fallback
            if not actual_supplier_tpin:
                print(f"WARNING: No tax_id found for supplier {supplier_name_from_crystal}")
        
        # Use the actual TPIN, fallback to Purchase Invoice supplier_tpin field
        supplier_tpin = actual_supplier_tpin or getattr(doc, "supplier_tpin", None)
        print(f"DEBUG: Final supplier_tpin for payload: {supplier_tpin}")
        supplier_branch_id = crystal_doc.supplier_branch_id or getattr(doc, "supplier_branch_id", "000")
        supplier_invoice_no = crystal_doc.supplier_invoice_no or get_supplier_invoice_number(doc.name)
        remarks = crystal_doc.remarks or doc.remarks or "No Remarks"
        
        # Get codes from Crystallised document
        regtycd = crystal_doc.regtycd or reg_ty_cd
        pchstycd = crystal_doc.pchstycd or "N"
        receipt_type_code = crystal_doc.receipt_type_code or rcpt_ty_cd
        payment_type_code = crystal_doc.payment_type_code or "01"
        pchssttscd = crystal_doc.pchssttscd or "02"
    else:
        # Fallback to Purchase Invoice calculations (shouldn't happen if workflow is correct)
        print("WARNING: Using Purchase Invoice values as fallback!")
        total_item_count = len(doc.items)
        total_taxable_amount = round(sum(float(i.base_net_amount) for i in doc.items), 4)
        total_tax_amount = round(sum(float(getattr(i, "item_tax_amount", 0)) for i in doc.items), 4)
        total_amount = round(float(doc.base_grand_total), 2)
        
        supplier_tpin = getattr(doc, "supplier_tpin", None)
        supplier_branch_id = getattr(doc, "supplier_branch_id", "000")
        supplier_invoice_no = get_supplier_invoice_number(doc.name)
        remarks = doc.remarks or "No Remarks"
        
        regtycd = reg_ty_cd
        pchstycd = "N"
        receipt_type_code = rcpt_ty_cd
        payment_type_code = "01"
        pchssttscd = "02"

    payload = {
        "tpin": tpin,
        "bhfId": branch_code,
        "cisInvcNo": f"cis_{doc.name}",
        "orgInvcNo": 0,
        "spplrTpin": supplier_tpin,
        "spplrBhfId": supplier_branch_id,
        "spplrNm": doc.supplier_name,
        "spplrInvcNo": supplier_invoice_no,
        "regTyCd": regtycd,
        "pchsTyCd": pchstycd,
        "rcptTyCd": receipt_type_code,
        "pmtTyCd": payment_type_code,
        "pchsSttsCd": pchssttscd,
        "cfmDt": now_datetime().strftime("%Y%m%d%H%M%S"),
        "pchsDt": now_datetime().strftime("%Y%m%d"),
        "cnclReqDt": "",
        "cnclDt": "",
        "totItemCnt": total_item_count,
        "totTaxblAmt": total_taxable_amount,
        "totTaxAmt": total_tax_amount,
        "totAmt": total_amount,
        "remark": remarks,
        "regrNm": frappe.session.user,
        "regrId": frappe.session.user,
        "modrNm": frappe.session.user,
        "modrId": frappe.session.user,
        "itemList": [],
    }

    # --- Build item list ---
    # IMPORTANT: If crystal_doc has items, use those instead of Purchase Invoice items
    if crystal_doc and hasattr(crystal_doc, 'items') and crystal_doc.items:
        print(f"Using items from Crystallised document: {len(crystal_doc.items)} items")
        for idx, item in enumerate(crystal_doc.items, start=1):
            item_data = {
                "itemSeq": idx,
                "itemCd": getattr(item, "item_code", None),
                "itemClsCd": getattr(item, "item_class_code", "00000000"),
                "itemNm": getattr(item, "item_name", ""),
                "bcd": getattr(item, "barcode", None),
                "pkgUnitCd": getattr(item, "packaging_unit_code", "EA"),
                "pkg": float(getattr(item, "package_qty", 0)),
                "qtyUnitCd": getattr(item, "quantity_unit_code", "EA"),
                "qty": float(getattr(item, "quantity", 0)),
                "prc": float(getattr(item, "unit_price", 0)),
                "splyAmt": float(getattr(item, "supply_amount", 0)),
                "dcRt": float(getattr(item, "discount_rate", 0)),
                "dcAmt": float(getattr(item, "discount_amount", 0)),
                "taxTyCd": getattr(item, "vat_category_code", "A"),
                "taxblAmt": round(float(getattr(item, "supply_amount", 0)), 2),
                "vatCatCd": getattr(item, "vat_category_code", "A"),
                "taxAmt": round(float(getattr(item, "vat_amount", 0)), 2),
                "totAmt": round(float(getattr(item, "total_amount", 0)), 2),
                "iplCatCd": None,
                "tlCatCd": None,
                "exciseCatCd": None,
                "iplTaxblAmt": None,
                "tlTaxblAmt": None,
                "exciseTaxblAmt": None,
                "iplAmt": None,
                "tlAmt": None,
                "exciseTxAmt": None,
            }
            payload["itemList"].append(item_data)
    else:
        # Fallback to Purchase Invoice items
        print("Using items from Purchase Invoice")
        for idx, item in enumerate(doc.items, start=1):
            pkg_code = frappe.db.get_value("Item", item.item_code, "custom_smart_packaging_unit") or "EA"
            class_code = frappe.db.get_value("Item", item.item_code, "custom_smart_item_classification_code") or "00000000"
            uom_code = frappe.db.get_value("Item", item.item_code, "custom_smart_quantity_unit") or "EA"

            item_data = {
                "itemSeq": idx,
                "itemCd": getattr(item, "item_code", None),
                "itemClsCd": class_code,
                "itemNm": item.item_name,
                "bcd": getattr(item, "barcode", None),
                "pkgUnitCd": pkg_code,
                "pkg": float(getattr(item, "package_qty", 0)),
                "qtyUnitCd": uom_code,
                "qty": float(item.qty),
                "prc": float(item.base_rate),
                "splyAmt": float(item.base_net_amount),
                "dcRt": float(getattr(item, "discount_percentage", 0)),
                "dcAmt": float(getattr(item, "discount_amount", 0)),
                "taxTyCd": getattr(item, "custom_tax_type", "A"),
                "taxblAmt": round(float(item.base_net_amount), 2),
                "vatCatCd": "A",
                "taxAmt": round(float(getattr(item, "item_tax_amount", 0)), 2),
                "totAmt": round(float(item.base_amount), 2),
                "iplCatCd": None,
                "tlCatCd": None,
                "exciseCatCd": None,
                "iplTaxblAmt": None,
                "tlTaxblAmt": None,
                "exciseTaxblAmt": None,
                "iplAmt": None,
                "tlAmt": None,
                "exciseTxAmt": None,
            }
            payload["itemList"].append(item_data)

    return payload


def generate_vsdc_item_payload(item_name: str, bhfid, settings_name: str) -> dict:
	item = frappe.get_doc("Item", item_name)

	def get_code(fieldname: str) -> str | None:
		if not item.get(fieldname):
			return None
		link_doctype = item.meta.get_field(fieldname).options
		link_value = item.get(fieldname)

		# map Item field → correct code field in linked Doctype
		field_map = {
			"custom_smart_item_classification_code": "item_cls_cd",
			"custom_smart_item_type": "class_code",
			"custom_smart_country_of_origin": "class_code",
			"custom_smart_packaging_unit_code": "class_code",
			"custom_smart_quantity_unit_code": "class_code",
			"custom_vat_category_code": "code",
			"ipl_category_code": "class_code",
			"trade_levy_category": "class_code",
			"excise_tax_category": "class_code",
			"rental_income_status": "class_code",
			"insurance_applicable": "class_code",
		}

		code_field = field_map.get(fieldname, "code")  # fallback to `code` if unsure

		return frappe.db.get_value(link_doctype, link_value, code_field)

		# Fetch first settings record

	settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)

	tpin = settings.get("tpin")
	# if settings:
	# 	settings_name = settings[0]["name"]
	# 	tpin = (
	# 		get_decrypted_password(
	# 			"Crystal ZRA Smart Invoice Settings", settings_name, "tpin", raise_exception=False
	# 		)
	# 		or ""
	# 	)
	# --- Get BhfId from Settings ---
	# bhf_id = frappe.db.get_single_value("Crystal ZRA Smart Invoice Settings", "branch_id") or "000"

	payload = {
		"tpin": tpin,
		"bhfid": bhfid,
		"itemCd": item.custom_smart_item_code,  # Generate a custom smart_item_code
		"itemClsCd": get_code("custom_smart_item_classification_code"),
		"itemTyCd": item.custom_smart_item_type,
		"itemNm": item.item_name,
		"itemStdNm": item.item_name,
		"orgnNatCd": get_code("custom_smart_country_of_origin_"),
		"pkgUnitCd": get_code("custom_smart_packaging_unit"),
		"qtyUnitCd": get_code("custom_smart_quantity_unit"),
		"vatCatCd": get_code("custom_vat_category_code"),
		"iplCatCd": get_code("custom_smart_insurance_premium_levy"),
		"tlCatCd": get_code("custom_smart_tourism_levy"),
		"exciseTxCatCd": get_code("custom_smart_excise_duties_"),
		"btchNo": item.get("batch_number") or None,
		"bcd": item.get("barcode") or None,
		"dftPrc": float(item.valuation_rate),
		"manufacturerTpin": item.get("custom_manufacture_tpin") or None,
		"manufacturerItemCd": item.get("custom_manufacturer_item_code") or None,
		"rrp": float(item.get("standard_rate") or 0),
		"svcChargeYn": "Y" if item.get("is_service_charge_applicable") else "N",
		"rentalYn": "Y" if item.get("custom_smart_rental_income_applicable") else "N",
		"addInfo": item.get("additional_info") or None,
		"sftyQty": float(item.get("safety_stock") or 0),
		"isrcAplcbYn": "Y" if item.get("custom_smart_insurance_applicable") else "N",
		"useYn": "Y" if item.disabled == 0 else "N",
		"regrNm": frappe.session.user,
		"regrId": frappe.session.user,
		"modrNm": frappe.session.user,
		"modrId": frappe.session.user,
	}

	return payload


def fmt4(value):
	try:
		return float(round(float(value or 0), 4))
	except Exception:
		return 0.0


def build_invoice_payload(invoice: "Document", settings_name: str) -> dict:
	# settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)

	settings = get_settings(settings_name)
	tpin = settings.get("tpin")
	branch_code = "000"
	try:
		if hasattr(invoice, "branch") and invoice.branch:
			branch_doc = frappe.get_doc("Branch", invoice.branch)
			branch_code = branch_doc.get("custom_branch_code") or "000"
	except Exception as e:
		frappe.log_error(f"Failed to fetch branch code: {e}", "Branch Code Error")

	# Dates
	sales_dt = datetime.strptime(str(invoice.posting_date), "%Y-%m-%d").strftime("%Y%m%d")
	now_str = datetime.now().strftime("%Y%m%d%H%M%S")

	# Make cisInvcNo unique by appending timestamp to avoid duplicates on resubmission
	reference_number = f"{invoice.name}-{now_str}"
	customer = frappe.get_doc("Customer", invoice.customer)

	tax_field_map = {
		"A": ("taxblAmtA", "taxAmtA", "taxRtA"),
		"B": ("taxblAmtB", "taxAmtB", "taxRtB"),
		"C1": ("taxblAmtC1", "taxAmtC1", "taxRtC1"),
		"C2": ("taxblAmtC2", "taxAmtC2", "taxRtC2"),
		"C3": ("taxblAmtC3", "taxAmtC3", "taxRtC3"),
		"D": ("taxblAmtD", "taxAmtD", "taxRtD"),
		"F": ("taxblAmtF", "taxAmtF", "taxRtF"),
		"IPL1": ("taxblAmtIpl1", "taxAmtIpl1", "taxRtIpl1"),
		"IPL2": ("taxblAmtIpl2", "taxAmtIpl2", "taxRtIpl2"),
		"TL": ("taxblAmtTl", "taxAmtTl", "taxRtTl"),
	}

	payload = {
		"tpin": tpin,
		"bhfId": branch_code or "000",
		"cisInvcNo": reference_number,
		"salesDt": sales_dt,
		"custTpin": customer.tax_id,
		"custNm": customer.customer_name,
		"currencyTyCd": invoice.currency,
		"totItemCnt": len(invoice.items),
		"totAmt": fmt4(0),
		"totTaxAmt": fmt4(0),
		"totTaxblAmt": fmt4(0),
		"remark": invoice.remarks or "",
		"cfmDt": now_str,
		"regrId": "admin",
		"regrNm": "admin",
		"modrId": "admin",
		"modrNm": "admin",
		"pmtTyCd": "01",
		"rcptTyCd": "S",
		"salesTyCd": "N",
		"salesSttsCd": "02",
		"saleCtyCd": "1",
		"prchrAcptcYn": "N",
		"orgInvcNo": 0,
		"exchangeRt": 1,
		"itemList": [],
	}

	# Conditionally add lpoNumber only if valid (9-20 characters)
	lpo_number = invoice.get("custom_lpo_number")
	if lpo_number and 9 <= len(lpo_number) <= 20:
		payload["lpoNumber"] = lpo_number

	# Initialize tax category fields
	for _, (taxbl, taxamt, taxrt) in tax_field_map.items():
		payload[taxbl] = fmt4(0)
		payload[taxamt] = fmt4(0)
		payload[taxrt] = 0

	# Line items
	for idx, item in enumerate(invoice.items, start=1):
		# Fetch custom codes
		pkg_code = frappe.db.get_value("Item", item.item_code, "custom_smart_packaging_unit") or "EA"
		class_code = (
			frappe.db.get_value("Item", item.item_code, "custom_smart_item_classification_code") or "00000000"
		)
		uom_code = frappe.db.get_value("Item", item.item_code, "custom_smart_quantity_unit") or "EA"

		qty = fmt4(item.qty)
		rate = fmt4(item.rate)

		# Supply amount = net amount before tax
		# sply_amt = fmt4(item.net_amount)

		actual_sply_amt = fmt4(rate * qty)
		sply_amt = actual_sply_amt

		# Discount
		dc_amt = fmt4(item.get("discount_amount") or 0)
		dc_rt = fmt4(item.get("discount_percentage") or 0)

		# Tax rate
		tax_rate = float(item.get("custom_tax_rate") or 0)

		# MTV Logic
		is_mtv = invoice.get("custom_is_mtv")
		rrp_raw = (
			item.get("custom_rrp")
			or item.get("standard_rate")
			or frappe.db.get_value("Item", item.item_code, "custom_rrp")
			or frappe.db.get_value("Item", item.item_code, "standard_rate")
			or 0
		)
		
		# Format RRP properly - for MTV, use RRP if available, otherwise use rate
		rrp = fmt4(rrp_raw if rrp_raw > 0 else rate)

		if is_mtv and rrp_raw > _safe_float(rate):
			# Use MTV for tax calculation
			taxable_amt = fmt4(_safe_float(rrp_raw) * _safe_float(qty))
			vat_amt = fmt4(taxable_amt * tax_rate / 100)
			# sply_amt in ZRA payload (vatTaxblAmt) should reflect MTV
			sply_amt = taxable_amt
			# Track that MTV was applied
			invoice.custom_mtv_applied = 1
		else:
			vat_amt = fmt4(sply_amt * tax_rate / 100)

		vat_rate = fmt4(_safe_float(rate) * tax_rate / 100)
		item_code = (
			item.get("custom_smart_item_code")
			or frappe.db.get_value("Item", item.item_code, "custom_smart_item_code")
			or item.item_code
		)
		
		# Totals
		tot_amt = fmt4(actual_sply_amt - dc_amt + vat_amt)
		tl_amt = tot_amt

		sply_rate = fmt4(_safe_float(rate) + vat_rate)
		# tl_amt = fmt4(sply_amt + vat_amt)   # line total including VAT
		# tot_amt = fmt4(sply_amt - dc_amt + vat_amt)  # supply - discount + taxes

		# Update tax category totals
		vat_cat = item.get("custom_taxation_type") or "A"
		
		# MTV Enforcement: Only Category B allowed for MTV
		if is_mtv:
			vat_cat = "B"
			
		if vat_cat in tax_field_map:
			taxbl, taxamt, taxrt = tax_field_map[vat_cat]

			# For MTV, we only populate 'B' (which is now forced if is_mtv is true)
			payload[taxbl] = fmt4(payload[taxbl] + sply_amt)
			payload[taxamt] = fmt4(payload[taxamt] + vat_amt)
			payload[taxrt] = int(round(tax_rate))

		# Item block
		payload["itemList"].append(
			{
				"itemSeq": idx,
				"itemCd": item_code,
				"itemNm": item.item_name,
				"itemClsCd": class_code,
				"qty": qty,
				"qtyUnitCd": uom_code,
				"prc": sply_rate,
				"splyAmt": tl_amt,
				"vatAmt": vat_amt,
				"tlAmt": 0,
				"totAmt": tot_amt,
				"vatTaxblAmt": sply_amt,
				"tlTaxblAmt": sply_amt,
				"pkg": item.get("package_qty") or 1,
				"pkgUnitCd": pkg_code,
				"dcAmt": dc_amt,
				"dcRt": dc_rt,
				"bcd": item.barcode or "",
				"vatCatCd": vat_cat,
				"rrp": rrp,
			}
		)

	# Update global totals AFTER items
	payload["totAmt"] = sum(item["totAmt"] for item in payload["itemList"])
	payload["totTaxAmt"] = sum(item["vatAmt"] for item in payload["itemList"])
	payload["totTaxblAmt"] = sum(item["vatTaxblAmt"] for item in payload["itemList"])

	return payload


def get_invoice_reference_number(invoice: Document) -> str:
	"""
	Generate a unique reference number for Crystal VSDC invoice submissions.

	Rules:
	- Use the ERPNext document name as the base reference (e.g., SINV-0001).
	- If the invoice has revisions (`revision_count > 0`), append `-R{revision_count}`
	  to distinguish resubmissions (e.g., SINV-0001-R1).
	- This ensures Crystal VSDC can differentiate between original and updated invoices.

	Args:
	    invoice (Document): The Invoice document instance.

	Returns:
	    str: Unique reference number for submission to Crystal VSDC.
	"""
	reference_number = invoice.name
	if getattr(invoice, "revision_count", 0):
		reference_number = f"{invoice.name}-R{int(invoice.revision_count)}"
	return reference_number


def build_credit_note_payload(doc, settings_name):
	"""Build payload for Credit Note (Return Invoice) matching invoice payload structure."""

	# settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
	original_invoice = frappe.get_doc("Sales Invoice", doc.return_against)
	customer = frappe.get_doc("Customer", doc.customer)
	# org_invc_no = original_invoice.get("custom_scu_invoice_number")
	settings = get_settings(settings_name)
	tpin = settings.get("tpin")

	branch_code = "000"
	try:
		if hasattr(original_invoice, "branch") and original_invoice.branch:
			branch_doc = frappe.get_doc("Branch", original_invoice.branch)
			branch_code = branch_doc.get("custom_branch_code") or "000"
	except Exception as e:
		frappe.log_error(f"Failed to fetch branch code: {e}", "Branch Code Error")

	def extract_numeric(invoice_id: str) -> str:
		"""
		Extract the last numeric segment of an invoice ID that is not all zeros.
		Example:
			SI-INV-2025-00492 -> '492'
			SI-INV-2025-00000 -> fallback to full string or None
		"""
		# Find all sequences of digits
		matches = re.findall(r"\d+", invoice_id)
		# Reverse iterate to find the first non-zero numeric string
		for num in reversed(matches):
			if int(num) != 0:
				return str(int(num))  # Convert to remove leading zeros
		return invoice_id  # fallback if all numbers are zerod

	sales_dt = getdate(doc.posting_date).strftime("%Y%m%d")
	now_str = now_datetime().strftime("%Y%m%d%H%M%S")

	# === Tax category mapping ===
	tax_field_map = {
		"A": ("taxblAmtA", "taxAmtA", "taxRtA"),
		"B": ("taxblAmtB", "taxAmtB", "taxRtB"),
		"C1": ("taxblAmtC1", "taxAmtC1", "taxRtC1"),
		"C2": ("taxblAmtC2", "taxAmtC2", "taxRtC2"),
		"C3": ("taxblAmtC3", "taxAmtC3", "taxRtC3"),
		"F": ("taxblAmtF", "taxAmtF", "taxRtF"),
		"IPL1": ("taxblAmtIpl1", "taxAmtIpl1", "taxRtIpl1"),
		"IPL2": ("taxblAmtIpl2", "taxAmtIpl2", "taxRtIpl2"),
		"TL": ("taxblAmtTl", "taxAmtTl", "taxRtTl"),
	}

	# === Base payload ===
	payload = {
		"tpin": tpin,
		"bhfId": branch_code,
		"orgInvcNo": original_invoice.custom_current_receipt_number,
		"cisInvcNo": doc.name,
		"custTpin": customer.tax_id or "",
		"custNm": doc.customer_name or "",
		"salesTyCd": "N",
		"rcptTyCd": "R",  # R = Credit Note
		"pmtTyCd": get_payment_type_code(doc),
		"salesSttsCd": "02",  # Return
		"cfmDt": now_str,
		"salesDt": sales_dt,
		"rfdRsnCd": "01",
		"invcAdjustReason": doc.get("return_reason") or "Return Credit",
		"totItemCnt": len(doc.items),
		"cashDcRt": 0,
		"cashDcAmt": 0,
		"totAmt": 0,
		"totTaxAmt": 0,
		"totTaxblAmt": 0,
		"prchrAcptcYn": "N",
		"remark": doc.remarks or "",
		"regrId": frappe.session.user,
		"regrNm": frappe.utils.get_fullname(frappe.session.user),
		"modrId": frappe.session.user,
		"modrNm": frappe.utils.get_fullname(frappe.session.user),
		"saleCtyCd": "1",
		"currencyTyCd": doc.currency or "ZMW",
		"exchangeRt": "1",
		"itemList": [],
	}

	# Initialize all tax fields to 0
	for _, (taxbl, taxamt, taxrt) in tax_field_map.items():
		payload[taxbl] = 0
		payload[taxamt] = 0
		payload[taxrt] = 0

	# === Build line items ===
	for idx, item in enumerate(doc.items, start=1):
		pkg_code = frappe.db.get_value("Item", item.item_code, "custom_smart_packaging_unit") or "EA"
		class_code = (
			frappe.db.get_value("Item", item.item_code, "custom_smart_item_classification_code") or "00000000"
		)
		uom_code = frappe.db.get_value("Item", item.item_code, "custom_smart_quantity_unit") or "EA"

		qty = abs(fmt4(item.qty))
		rate = abs(fmt4(item.rate))
		sply_amt = abs(fmt4(rate * qty))

		dc_amt = abs(fmt4(item.discount_amount))
		dc_rt = abs(fmt4(item.discount_percentage))

		tax_rate = abs(float(item.get("custom_tax_rate") or 0))
		vat_rate = fmt4(rate * tax_rate / 100)
		sply_rate = fmt4(rate + vat_rate)
		vat_amt = abs(fmt4(sply_amt * tax_rate / 100))
		tot_amt = abs(fmt4(sply_amt - dc_amt + vat_amt))
		tl_amt = tot_amt
		item_code = (
			item.get("custom_smart_item_code")
			or frappe.db.get_value("Item", item.item_code, "custom_smart_item_code")
			or item.item_code
		)
		vat_cat = get_vat_category(item)

		# Update tax fields by category
		if vat_cat in tax_field_map:
			taxbl, taxamt, taxrt = tax_field_map[vat_cat]
			payload[taxbl] = fmt4(payload[taxbl] + sply_amt)
			payload[taxamt] = fmt4(payload[taxamt] + vat_amt)
			payload[taxrt] = int(round(tax_rate))

		payload["itemList"].append(
			{
				"itemSeq": idx,
				"itemCd": item_code,
				"itemNm": item.item_name,
				"itemClsCd": class_code,
				"qty": qty,
				"qtyUnitCd": uom_code,
				"prc": sply_rate,
				"splyAmt": tl_amt,
				"vatAmt": vat_amt,
				"tlAmt": 0,
				"totAmt": tot_amt,
				"vatTaxblAmt": sply_amt,
				"tlTaxblAmt": sply_amt,
				"pkg": abs(item.get("package_qty") or 1),
				"pkgUnitCd": pkg_code,
				"dcAmt": dc_amt,
				"dcRt": dc_rt,
				"bcd": item.barcode or "",
				"vatCatCd": vat_cat,
				"rrp": 0,
			}
		)

	# === Totals ===
	payload["totAmt"] = fmt4(sum(i["totAmt"] for i in payload["itemList"]))
	payload["totTaxAmt"] = fmt4(sum(i["vatAmt"] for i in payload["itemList"]))
	payload["totTaxblAmt"] = fmt4(sum(i["vatTaxblAmt"] for i in payload["itemList"]))

	return payload


def get_vat_category(item):
	"""
	Map ERPNext item tax or tax template to ZRA VAT category code.
	Categories (ZRA standard):
	    A = Standard-rated (16%)
	    B = Zero-rated
	    C = Exempt
	    D = Non-taxable
	"""
	# If you store VAT category in a custom field, just return it
	if getattr(item, "custom_taxation_type", None):
		return item.custom_taxation_type

	# Try to infer from tax rate or tax template
	tax_rate = 0
	try:
		if hasattr(item, "custom_tax_rate") and isinstance(item.custom_tax_rate, dict):
			# ERPNext stores tax rates as JSON
			tax_rate = next(iter(item.custom_tax_rate.values()))
	except Exception:
		pass

	#  Fallbacks
	if tax_rate >= 16:
		return "A"  # Standard-rated
	elif tax_rate == 0:
		return "B"  # Zero-rated
	elif tax_rate is None:
		return "C"  # Exempt
	else:
		return "D"  # Non-taxable


def get_payment_type_code(doc):
	"""
	Map ERPNext payment method(s) to ZRA payment type codes.

	ZRA Codes:
	  01 = Cash
	  02 = Credit
	  03 = Cheque
	  04 = Electronic Payment (Card, Bank Transfer, Mobile Money)
	  05 = Other
	"""

	# Default to "01" = Cash
	payment_code = "01"

	try:
		# POS Invoice usually has payment references
		if hasattr(doc, "payments") and doc.payments:
			for payment in doc.payments:
				mode = (payment.mode_of_payment or "").lower()
				if "cash" in mode:
					payment_code = "01"
				elif "credit" in mode:
					payment_code = "02"
				elif "cheque" in mode:
					payment_code = "03"
				elif any(x in mode for x in ["bank", "transfer", "mobile", "card", "visa", "master"]):
					payment_code = "04"
				else:
					payment_code = "05"
		else:
			# For Sales Invoice, check the `mode_of_payment` field or payment schedule
			if hasattr(doc, "mode_of_payment") and doc.mode_of_payment:
				mode = doc.mode_of_payment.lower()
				if "cash" in mode:
					payment_code = "01"
				elif "credit" in mode:
					payment_code = "02"
				elif "cheque" in mode:
					payment_code = "03"
				elif any(x in mode for x in ["bank", "transfer", "mobile", "card"]):
					payment_code = "04"
				else:
					payment_code = "05"
	except Exception:
		pass

	return payment_code


def build_stock_payload(tpin, bhf_id, user, stock_items, route_key=None, warehouse=None):
	if not isinstance(stock_items, list):
		raise ValueError("stock_items must be a list of dicts")

	user = user or "Admin"

	# SaveStockItems — detailed stock movement
	if route_key and route_key.lower() == "savestockitems":
		item_list = []
		for i, item in enumerate(stock_items, start=1):
			item_code = item.get("itemCd")
			item_doc = (
				frappe.db.get_value(
					"Item",
					item_code,
					["item_name", "custom_smart_item_classification_code", "valuation_rate"],
					as_dict=True,
				)
				or {}
			)
			class_code = item_doc.get("custom_smart_item_classification_code")
			item_name = item_doc.get("item_name")
			price = float(item.get("prc") or 0)
			qty = float(item.get("qty") or 1)
			tax_rate = 0.16  # Get this dynamically based on configuration
			tax_amt = round(price * qty * tax_rate / (1 + tax_rate), 2)
			taxable_amt = round(price * qty - tax_amt, 2)

			item_list.append(
				{
					"itemSeq": i,
					"itemCd": item_code,
					"itemClsCd": class_code,
					"itemNm": item_name,
					"pkgUnitCd": "BA",
					"qtyUnitCd": "BE",
					"qty": qty,
					"prc": price,
					"splyAmt": price * qty,
					"taxblAmt": taxable_amt,
					"vatCatCd": "A",
					"taxAmt": tax_amt,
					"totAmt": price * qty,
				}
			)

		payload = {
			"tpin": tpin,
			"bhfId": bhf_id,
			"sarNo": 1,
			"orgSarNo": 0,
			"regTyCd": "M",
			"custTpin": None,
			"custNm": None,
			"custBhfId": None,
			"sarTyCd": "02",
			"ocrnDt": now().split(" ")[0].replace("-", ""),
			"totItemCnt": len(item_list),
			"totTaxblAmt": round(sum(i["taxblAmt"] for i in item_list), 2),
			"totTaxAmt": round(sum(i["taxAmt"] for i in item_list), 2),
			"totAmt": round(sum(i["totAmt"] for i in item_list), 2),
			"remark": None,
			"regrId": user,
			"regrNm": user,
			"modrNm": user,
			"modrId": user,
			"itemList": item_list,
		}

	# SaveStockMaster — stock summary update
	else:
		stock_item_list = []

		for i in stock_items:
			item_code = i.get("itemCd")
			if not item_code:
				continue

			if warehouse:
				# Get balance quantity from the specified warehouse
				current_qty = (
					frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
					or 0
				)
			else:
				# Aggregate quantity across all warehouses
				current_qty = (
					frappe.db.get_all(
						"Bin", filters={"item_code": item_code}, fields=["sum(actual_qty) as qty"]
					)[0].qty
					or 0
				)

			# Subtract the sold quantity from current stock
			sold_qty = float(i.get("qty", 0))
			remaining_qty = float(current_qty) - sold_qty

			stock_item_list.append(
				{
					"itemCd": item_code,
					"rsdQty": remaining_qty,
				}
			)

		payload = {
			"tpin": tpin,
			"bhfId": bhf_id,
			"regrId": user,
			"regrNm": user,
			"modrNm": user,
			"modrId": user,
			"stockItemList": stock_item_list,
		}

	return payload


def build_stock_item_payload(doc):
	"""
	Builds payload for /api/v1/StockItemInformation/SaveStockItems
	from stock movement documents (Sales Invoice, Purchase Receipt, Stock Entry, etc.)
	"""
	if isinstance(doc, str):
		doc = frappe.get_doc(doc)

	company_tpin = (
		frappe.db.get_value("Crystal ZRA Smart Invoice Settings", {"company": doc.company}, "tpin") or ""
	)
	user = frappe.session.user or "Admin"
	sar_no = int(re.sub(r"\D", "", doc.name)[-5:]) or 1

	# Get all stock-impacting items
	items = getattr(doc, "items", [])
	item_list = []
	for i, item in enumerate(items, start=1):
		item_doc = frappe.get_doc("Item", item.item_code)
		class_code = getattr(item_doc, "custom_class_code", None) or "50102517"

		qty = float(item.qty)
		price = float(item.rate)
		tax_rate = float(getattr(item, "tax_rate", 16.0)) / 100
		tax_amt = price * qty * (tax_rate / (1 + tax_rate))
		taxable_amt = (price * qty) - tax_amt

		item_list.append(
			{
				"itemSeq": i,
				"itemCd": item.item_code,
				"itemClsCd": class_code,
				"itemNm": item.item_name,
				"pkgUnitCd": "BA",
				"qtyUnitCd": "BE",
				"qty": qty,
				"prc": price,
				"splyAmt": float(item.amount),
				"taxblAmt": round(taxable_amt, 2),
				"vatCatCd": "A",
				"taxAmt": round(tax_amt, 2),
				"totAmt": float(item.amount),
			}
		)

	payload = {
		"tpin": company_tpin,
		"bhfId": "000",
		"sarNo": sar_no,
		"orgSarNo": 0,
		"regTyCd": "M",
		"custTpin": None,
		"custNm": None,
		"custBhfId": None,
		"sarTyCd": "02",  # "02" = stock out (e.g. sale)
		"ocrnDt": doc.posting_date.strftime("%Y%m%d")
		if getattr(doc, "posting_date", None)
		else now().split(" ")[0],
		"totItemCnt": len(item_list),
		"totTaxblAmt": round(sum(i["taxblAmt"] for i in item_list), 2),
		"totTaxAmt": round(sum(i["taxAmt"] for i in item_list), 2),
		"totAmt": round(sum(i["totAmt"] for i in item_list), 2),
		"remark": getattr(doc, "remarks", None),
		"regrId": user,
		"regrNm": user,
		"modrNm": user,
		"modrId": user,
		"itemList": item_list,
	}

	return payload


def build_sales_payload(sales_invoice_name, company_tpin, user="Admin"):
	"""Builds ZRA Smart Invoice payload from Sales Invoice."""
	inv = frappe.get_doc("Sales Invoice", sales_invoice_name)
	item_list = []

	for i, item in enumerate(inv.items, start=1):
		item_doc = frappe.get_doc("Item", item.item_code)
		class_code = getattr(item_doc, "custom_class_code", None)
		tax_rate = float(getattr(item, "tax_rate", 16.0)) / 100
		tax_amt = item.amount - (item.amount / (1 + tax_rate))
		taxable_amt = item.amount - tax_amt
		item_list.append(
			{
				"itemSeq": i,
				"itemCd": item.item_code,
				"itemClsCd": class_code,
				"itemNm": item.item_name,
				"pkgUnitCd": "BA",
				"qtyUnitCd": "BE",
				"qty": float(item.qty),
				"prc": float(item.rate),
				"splyAmt": float(item.amount),
				"taxblAmt": round(taxable_amt, 2),
				"vatCatCd": "A",  # You can map VAT category dynamically later
				"taxAmt": round(tax_amt, 2),
				"totAmt": float(item.amount),
			}
		)
	sar_no = int(re.sub(r"\D", "", inv.name)[-5:]) or 1

	payload = {
		"request": "SalesInvoice",
		"tpin": company_tpin,
		"bhfId": "000",
		"sarNo": sar_no,
		"orgSarNo": 0,
		"regTyCd": "M",
		"custTpin": getattr(inv, "customer_tpin", None),
		"custNm": inv.customer_name,
		"custBhfId": None,
		"sarTyCd": "02",  # 02 = Normal Sale
		"ocrnDt": inv.posting_date.strftime("%Y%m%d"),
		"totItemCnt": len(inv.items),
		"totTaxblAmt": round(sum(i["taxblAmt"] for i in item_list), 2),
		"totTaxAmt": round(sum(i["taxAmt"] for i in item_list), 2),
		"totAmt": float(inv.grand_total),
		"remark": inv.remarks or "",
		"regrId": user,
		"regrNm": user,
		"modrNm": user,
		"modrId": user,
		"itemList": item_list,
	}

	return payload


def generate_custom_item_code_smart(doc: Document) -> str:
	"""
	Generate smart item code in fixed format:
	    CC T PP QQ CCCC SSSSSSS

	    CC  = Country (2 chars)
	    T   = Item type (1 char)
	    PP  = Packaging unit (2 chars)
	    QQ  = Qty unit (2 chars)
	    CCCC = Classification code (4 chars, padded)
	    SSSSSSS = Running sequence (7 digits)
	"""

	# --- Extract fields ---
	country = (doc.get("custom_smart_country_of_origin_") or "").upper().strip()[:2]
	item_type = (doc.get("custom_smart_item_type") or "").upper().strip()[:1]
	pkg_unit = (doc.get("custom_smart_packaging_unit") or "").upper().strip()[:2]
	qty_unit = (doc.get("custom_smart_quantity_unit") or "").upper().strip()[:2]
	class_code = (doc.get("custom_smart_item_classification_code") or "").strip()

	# --- Enforce padding ---
	country = country.ljust(2)
	item_type = item_type.ljust(1)
	pkg_unit = pkg_unit.ljust(2)
	qty_unit = qty_unit.ljust(
		2,
	)
	class_code = class_code.zfill(4)  # always 4 digits

	# --- Build prefix ---
	prefix = f"{country}{item_type}{pkg_unit}{qty_unit}{class_code}"

	# --- Determine suffix ---
	if doc.get("custom_smart_item_code"):
		suffix = doc.custom_smart_item_code[-7:]
	else:
		last = frappe.db.sql(
			"""
            SELECT custom_smart_item_code
            FROM `tabItem`
            WHERE custom_smart_item_classification_code = %s
              AND custom_smart_item_code IS NOT NULL
            ORDER BY CAST(RIGHT(custom_smart_item_code, 7) AS UNSIGNED) DESC
            LIMIT 1
            """,
			(doc.custom_smart_item_classification_code,),
		)

		if last:
			last_code = last[0][0]
			try:
				suffix = str(int(last_code[-7:]) + 1).zfill(7)
			except:
				suffix = "0000001"
		else:
			suffix = "0000001"

	# --- Final smart code ---
	new_code = f"{prefix}{suffix}"

	# Save
	doc.db_set("custom_smart_item_code", new_code, update_modified=False)

	frappe.logger().info(f"[SMART] Generated Smart Code: {new_code}")

	return new_code


def build_import_item_payload(settings: dict):
	return {"company_name": settings.company, "tpin": settings.tpin}


def get_branch_code_from_sle(sle: dict) -> str:
	"""Return branch code from the document that generated the SLE."""

	voucher_type = sle.get("voucher_type")
	voucher_no = sle.get("voucher_no")

	if not voucher_type or not voucher_no:
		return "000"

	if not frappe.db.exists(voucher_type, voucher_no):
		return "000"

	doc = frappe.get_doc(voucher_type, voucher_no)

	# Branch may appear under different fieldnames
	branch_name = (
		getattr(doc, "branch", None)
		or getattr(doc, "custom_branch", None)
		or getattr(doc, "branch_id", None)
		or None
	)

	if not branch_name:
		return "000"

	# Fetch Branch master to get ZRA branch code
	branch_doc = frappe.get_doc("Branch", branch_name)

	branch_code = (
		getattr(branch_doc, "custom_branch_code", None)
		or getattr(branch_doc, "custom_branch_code", None)
		or "000"
	)

	return str(branch_code).zfill(3)


def build_rvat_sale_payload(docname: str, settings_name: str) -> dict:
	"""
	Build payload for RVAT Sale, supporting Principal ID and RVAT tax category.
	"""
	settings = get_settings(settings_name)
	tpin = settings.get("tpin")
	
	doc = frappe.get_doc("Sales Invoice", docname)

	branch_code = "000"
	try:
		if hasattr(doc, "branch") and doc.branch:
			branch_doc = frappe.get_doc("Branch", doc.branch)
			branch_code = branch_doc.get("custom_branch_code") or "000"
	except Exception as e:
		frappe.log_error(f"Failed to fetch branch code: {e}", "Branch Code Error")

	# Dates
	sales_dt = datetime.strptime(str(doc.posting_date), "%Y-%m-%d").strftime("%Y%m%d")
	now_str = datetime.now().strftime("%Y%m%d%H%M%S")

	# Make cisInvcNo unique by appending timestamp to avoid duplicates on resubmission
	reference_number = f"{doc.name}-{now_str}"
	customer = frappe.get_doc("Customer", doc.customer)

	# Extended tax map to include RVAT
	tax_field_map = {
		"A": ("taxblAmtA", "taxAmtA", "taxRtA"),
		"B": ("taxblAmtB", "taxAmtB", "taxRtB"),
		"C1": ("taxblAmtC1", "taxAmtC1", "taxRtC1"),
		"C2": ("taxblAmtC2", "taxAmtC2", "taxRtC2"),
		"C3": ("taxblAmtC3", "taxAmtC3", "taxRtC3"),
		"D": ("taxblAmtD", "taxAmtD", "taxRtD"),
		"F": ("taxblAmtF", "taxAmtF", "taxRtF"),
		"IPL1": ("taxblAmtIpl1", "taxAmtIpl1", "taxRtIpl1"),
		"IPL2": ("taxblAmtIpl2", "taxAmtIpl2", "taxRtIpl2"),
		"TL": ("taxblAmtTl", "taxAmtTl", "taxRtTl"),
		"RVAT": ("taxblAmtRvat", "taxAmtRvat", "taxRtRvat"),
		"E": ("taxblAmtE", "taxAmtE", "taxRtE"),
	}

	payload = {
		"tpin": tpin,
		"bhfId": branch_code or "000",
		"cisInvcNo": reference_number,
		"salesDt": sales_dt,
		"custTpin": customer.tax_id,
		"custNm": customer.customer_name,
		"currencyTyCd": doc.currency,
		"totItemCnt": len(doc.items),
		"totAmt": fmt4(0),
		"totTaxAmt": fmt4(0),
		"totTaxblAmt": fmt4(0),
		"remark": doc.remarks or "",
		"cfmDt": now_str,
		"regrId": frappe.session.user,
		"regrNm": frappe.session.user,
		"modrId": frappe.session.user,
		"modrNm": frappe.session.user,
		"pmtTyCd": "01",
		"rcptTyCd": "S",
		"salesTyCd": "N",
		"salesSttsCd": "02",
		"saleCtyCd": "1",
		"prchrAcptcYn": "N",
		"orgInvcNo": 0,
		"exchangeRt": 1,
		"itemList": [],
	}

	# Add Principal ID if present (RVAT Feature)
	if getattr(doc, "custom_principal_id", None):
		payload["principalId"] = doc.custom_principal_id

	# Initialize tax category fields
	for _, (taxbl, taxamt, taxrt) in tax_field_map.items():
		payload[taxbl] = fmt4(0)
		payload[taxamt] = fmt4(0)
		payload[taxrt] = 0
		
		# Set default rates for known categories if possible, otherwise they get updated from items
		if "Rvat" in taxbl: # taxblAmtRvat
			payload[taxrt] = 16

	# Line items
	for idx, item in enumerate(doc.items, start=1):
		# Fetch custom codes
		pkg_code = frappe.db.get_value("Item", item.item_code, "custom_smart_packaging_unit") or "EA"
		class_code = (
			frappe.db.get_value("Item", item.item_code, "custom_smart_item_classification_code") or "00000000"
		)
		uom_code = frappe.db.get_value("Item", item.item_code, "custom_smart_quantity_unit") or "EA"

		qty = fmt4(item.qty)
		rate = fmt4(item.rate)
		sply_amt = fmt4(rate * qty)

		dc_amt = fmt4(item.get("discount_amount") or 0)
		dc_rt = fmt4(item.get("discount_percentage") or 0)

		# Tax Logic
		vat_cat = item.get("custom_taxation_type") or "A"
		
		# If item is "RVAT", tax rate is 16%.
		if vat_cat == "RVAT":
			tax_rate = 16.0
		else:
			tax_rate = float(item.get("custom_tax_rate") or 0)

		# MTV Logic
		is_mtv = invoice.get("custom_is_mtv")
		rrp = (
			item.get("custom_rrp")
			or item.get("standard_rate")
			or frappe.db.get_value("Item", item.item_code, "custom_rrp")
			or frappe.db.get_value("Item", item.item_code, "standard_rate")
			or 0
		)
		
		actual_sply_amt = sply_amt
		if is_mtv and rrp > _safe_float(rate):
			# Use MTV for tax calculation
			taxable_amt = fmt4(_safe_float(rrp) * _safe_float(qty))
			vat_amt = fmt4(taxable_amt * tax_rate / 100)
			# taxable_amt is used for vatTaxblAmt and tlTaxblAmt
			sply_amt = taxable_amt
			# Track that MTV was applied
			invoice.custom_mtv_applied = 1
		else:
			vat_amt = fmt4(sply_amt * tax_rate / 100)

		vat_rate = fmt4(_safe_float(rate) * tax_rate / 100)
		
		item_code = (
			item.get("custom_smart_item_code")
			or frappe.db.get_value("Item", item.item_code, "custom_smart_item_code")
		)
		
		# Totals
		tot_amt = fmt4(actual_sply_amt - dc_amt + vat_amt)
		
		tl_amt = 0.0 

		sply_rate = fmt4(rate + vat_rate)

		# Update tax category totals
		if is_mtv:
			vat_cat = "B"
			
		if vat_cat in tax_field_map:
			taxbl, taxamt, taxrt = tax_field_map[vat_cat]
			payload[taxbl] = fmt4(payload[taxbl] + sply_amt)
			payload[taxamt] = fmt4(payload[taxamt] + vat_amt)
			payload[taxrt] = int(round(tax_rate))

		# Item block
		payload["itemList"].append(
			{
				"itemSeq": idx,
				"itemCd": item_code,
				"itemNm": item.item_name,
				"itemClsCd": class_code,
				"qty": qty,
				"qtyUnitCd": uom_code,
				"prc": sply_rate,
				"splyAmt": sply_amt, 
				"vatAmt": vat_amt,
				"tlAmt": tl_amt, 
				"totAmt": tot_amt,
				"vatTaxblAmt": sply_amt,
				"tlTaxblAmt": sply_amt,
				"pkg": item.get("package_qty") or 1,
				"pkgUnitCd": pkg_code,
				"dcAmt": dc_amt,
				"dcRt": dc_rt,
				"bcd": item.barcode or "",
				"vatCatCd": vat_cat,
				"rrp": rrp,
			}
		)

	# Update global totals
	payload["totAmt"] = sum(item["totAmt"] for item in payload["itemList"])
	payload["totTaxAmt"] = sum(item["vatAmt"] for item in payload["itemList"])
	payload["totTaxblAmt"] = sum(item["vatTaxblAmt"] for item in payload["itemList"])

	return payload

def build_export_sale_payload(docname: str, settings_name: str) -> dict:
	"""
	Build payload for Export Sales with destination country and zero-rated tax treatment.
	
	Export sales are identified by:
	- custom_is_export_sale checkbox = True
	- custom_destination_country field populated
	
	Key differences from domestic sales:
	- destnCountryCd: populated with destination country code (e.g., "MW" for Malawi)
	- saleCtyCd: remains "1" (same as domestic - destination country is the export indicator)
	- Tax category: typically C1 (Exports 0% - zero-rated)
	- Currency: may be foreign currency with actual exchange rate
	
	Args:
	    docname: Sales Invoice document name
	    settings_name: Crystal ZRA Smart Invoice Settings name
	    
	Returns:
	    dict: Export sale payload for ZRA API
	"""
	# Get settings and company TPIN
	settings = get_settings(settings_name)
	tpin = settings.get("tpin")
	
	# Fetch the Sales Invoice document
	doc = frappe.get_doc("Sales Invoice", docname)

	# Get branch code (default to "000" if not set)
	branch_code = "000"
	try:
		if hasattr(doc, "branch") and doc.branch:
			branch_doc = frappe.get_doc("Branch", doc.branch)
			branch_code = branch_doc.get("custom_branch_code") or "000"
	except Exception as e:
		frappe.log_error(f"Failed to fetch branch code: {e}", "Branch Code Error")

	# Format dates for ZRA API
	# salesDt: YYYYMMDD format (e.g., "20240508")
	# cfmDt: YYYYMMDDHHmmss format (e.g., "20240508102010")
	sales_dt = datetime.strptime(str(doc.posting_date), "%Y-%m-%d").strftime("%Y%m%d")
	now_str = datetime.now().strftime("%Y%m%d%H%M%S")

	# Use invoice name as reference number
	reference_number = doc.name
	
	# Fetch customer details
	customer = frappe.get_doc("Customer", doc.customer)

	# Get destination country code - THIS IS THE KEY EXPORT INDICATOR
	# For domestic sales, this field is empty ""
	# For export sales, this contains the country code (e.g., "MW" for Malawi)
	destination_country_code = ""
	if getattr(doc, "custom_destination_country", None):
		# Fetch the country code from the Crystallised Smart Country doctype
		destination_country_code = frappe.db.get_value(
			"Crystallised Smart Country", 
			doc.custom_destination_country, 
			"code"
		) or ""

	# Sale category code - IMPORTANT: Exports use "1" (same as domestic)
	# The destination country field is what indicates it's an export, not the sale category
	sale_category_code = "1"
	if getattr(doc, "custom_sale_category_code", None):
		sale_category_code = frappe.db.get_value(
			"Crystallised Smart Sale Category",
			doc.custom_sale_category_code,
			"code"
		) or "1"

	# Tax field mapping - maps VAT categories to payload field names
	# Each category has three fields: taxable amount, tax amount, and tax rate
	tax_field_map = {
		"A": ("taxblAmtA", "taxAmtA", "taxRtA"),           # Standard 16%
		"B": ("taxblAmtB", "taxAmtB", "taxRtB"),           # MTV 16%
		"C1": ("taxblAmtC1", "taxAmtC1", "taxRtC1"),       # Exports 0% - TYPICAL FOR EXPORTS
		"C2": ("taxblAmtC2", "taxAmtC2", "taxRtC2"),       # Zero-rated local 0%
		"C3": ("taxblAmtC3", "taxAmtC3", "taxRtC3"),       # Zero-rated by nature 0%
		"D": ("taxblAmtD", "taxAmtD", "taxRtD"),           # Exempt 0%
		"F": ("taxblAmtF", "taxAmtF", "taxRtF"),           # 10%
		"IPL1": ("taxblAmtIpl1", "taxAmtIpl1", "taxRtIpl1"), # Insurance Premium Levy 5%
		"IPL2": ("taxblAmtIpl2", "taxAmtIpl2", "taxRtIpl2"), # Insurance Premium Levy 0%
		"TL": ("taxblAmtTl", "taxAmtTl", "taxRtTl"),       # Tourism Levy 1.5%
	}

	# Get exchange rate - for foreign currency exports
	# If currency is ZMW (local), exchange rate is "1"
	# If foreign currency (USD, EUR, etc.), use the actual conversion rate
	exchange_rate = "1"
	if doc.currency != "ZMW":
		# Get exchange rate from invoice conversion_rate field
		exchange_rate = str(doc.conversion_rate or 1)

	# Build the main payload structure
	payload = {
		"tpin": tpin,                          # Company Tax Payer Identification Number
		"bhfId": branch_code or "000",         # Branch ID
		"cisInvcNo": reference_number,         # Invoice reference number (ERPNext doc name)
		"salesDt": sales_dt,                   # Sale date (YYYYMMDD)
		"custTpin": customer.tax_id or "",     # Customer TPIN (may be empty for foreign customers)
		"custNm": customer.customer_name,      # Customer name
		"currencyTyCd": doc.currency or "ZMW", # Currency code (ZMW, USD, EUR, etc.)
		"totItemCnt": len(doc.items),          # Total number of items
		"totAmt": fmt4(0),                     # Total amount (calculated later)
		"totTaxAmt": fmt4(0),                  # Total tax amount (calculated later)
		"totTaxblAmt": fmt4(0),                # Total taxable amount (calculated later)
		"remark": doc.remarks or "",           # Remarks/notes
		"cfmDt": now_str,                      # Confirmation datetime (YYYYMMDDHHmmss)
		"regrId": frappe.session.user,         # Registrar user ID
		"regrNm": frappe.session.user,         # Registrar user name
		"modrId": frappe.session.user,         # Modifier user ID
		"modrNm": frappe.session.user,         # Modifier user name
		"pmtTyCd": "01",                       # Payment type code (01 = Cash)
		"rcptTyCd": "S",                       # Receipt type code (S = Sale)
		"salesTyCd": "N",                      # Sales type code (N = Normal)
		"salesSttsCd": "02",                   # Sales status code (02 = Approved)
		"saleCtyCd": sale_category_code,       # Sale category (1 = Local, includes exports)
		"prchrAcptcYn": "N",                   # Purchaser acceptance (N = No)
		"orgInvcNo": 0,                        # Original invoice number (0 for new invoices)
		"exchangeRt": exchange_rate,           # Exchange rate (EXPORT-SPECIFIC: actual rate if foreign currency)
		"destnCountryCd": destination_country_code,  # EXPORT-SPECIFIC: Destination country code
		"itemList": [],                        # Item list (populated below)
	}

	# Initialize all tax category fields to zero
	# These will be accumulated as we process items
	for _, (taxbl, taxamt, taxrt) in tax_field_map.items():
		payload[taxbl] = fmt4(0)   # Taxable amount for this category
		payload[taxamt] = fmt4(0)  # Tax amount for this category
		payload[taxrt] = 0         # Tax rate for this category

	# Process each line item in the invoice
	for idx, item in enumerate(doc.items, start=1):
		# Fetch item-specific codes from Item master
		# These codes are required by ZRA for item classification
		pkg_code = frappe.db.get_value("Item", item.item_code, "custom_smart_packaging_unit") or "EA"
		class_code = (
			frappe.db.get_value("Item", item.item_code, "custom_smart_item_classification_code") or "00000000"
		)
		uom_code = frappe.db.get_value("Item", item.item_code, "custom_smart_quantity_unit") or "EA"

		# Get item quantities and pricing
		qty = fmt4(item.qty)                    # Quantity
		rate = fmt4(item.rate)                  # Unit rate (price per unit)
		sply_amt = fmt4(rate * qty)             # Supply amount (rate × quantity)

		# Get discount information
		dc_amt = fmt4(item.get("discount_amount") or 0)        # Discount amount
		dc_rt = fmt4(item.get("discount_percentage") or 0)     # Discount rate/percentage

		# Determine tax category and rate
		# For exports, default to C1 (Exports 0% - zero-rated)
		# User can override by setting custom_taxation_type on the item
		vat_cat = item.get("custom_taxation_type") or "C1"
		
		# Get tax rate from item or use 0 for zero-rated exports
		tax_rate = float(item.get("custom_tax_rate") or 0)
		
		# Calculate VAT amounts
		vat_rate = fmt4(rate * tax_rate / 100)      # VAT per unit
		vat_amt = fmt4(sply_amt * tax_rate / 100)   # Total VAT for this line
		
		# Get item code (ZRA item code or fallback to ERPNext item code)
		item_code = (
			item.get("custom_smart_item_code")
			or frappe.db.get_value("Item", item.item_code, "custom_smart_item_code")
			or item.item_code
		)
		
		# Get recommended retail price (RRP)
		rrp = item.get("standard_rate") or frappe.db.get_value("Item", item.item_code, "standard_rate")
		
		# Calculate line totals
		tot_amt = fmt4(sply_amt - dc_amt + vat_amt)  # Total = supply - discount + tax
		tl_amt = tot_amt                              # Tourism levy amount (same as total)
		sply_rate = fmt4(rate + vat_rate)             # Supply rate including VAT

		# Update tax category totals in the main payload
		# This accumulates amounts for each tax category across all items
		if vat_cat in tax_field_map:
			taxbl, taxamt, taxrt = tax_field_map[vat_cat]
			payload[taxbl] = fmt4(payload[taxbl] + sply_amt)   # Add to taxable amount
			payload[taxamt] = fmt4(payload[taxamt] + vat_amt)  # Add to tax amount
			payload[taxrt] = int(round(tax_rate))              # Set tax rate

		# Build item payload and add to item list
		payload["itemList"].append(
			{
				"itemSeq": idx,                # Item sequence number (1, 2, 3, ...)
				"itemCd": item_code,           # Item code (ZRA code)
				"itemNm": item.item_name,      # Item name
				"itemClsCd": class_code,       # Item classification code
				"qty": qty,                    # Quantity
				"qtyUnitCd": uom_code,         # Quantity unit code (EA, KG, etc.)
				"prc": sply_rate,              # Price (including VAT)
				"splyAmt": tl_amt,             # Supply amount
				"vatAmt": vat_amt,             # VAT amount
				"tlAmt": 0,                    # Tourism levy amount (0 for exports)
				"totAmt": tot_amt,             # Total amount for this line
				"vatTaxblAmt": sply_amt,       # VAT taxable amount
				"tlTaxblAmt": sply_amt,        # Tourism levy taxable amount
				"pkg": item.get("package_qty") or 1,  # Package quantity
				"pkgUnitCd": pkg_code,         # Package unit code
				"dcAmt": dc_amt,               # Discount amount
				"dcRt": dc_rt,                 # Discount rate
				"bcd": item.barcode or "",     # Barcode
				"vatCatCd": vat_cat,           # VAT category code (C1 for exports)
				"rrp": rrp,                    # Recommended retail price
			}
		)

	# Calculate and update global totals from all items
	# These are the invoice-level totals
	payload["totAmt"] = sum(item["totAmt"] for item in payload["itemList"])           # Total invoice amount
	payload["totTaxAmt"] = sum(item["vatAmt"] for item in payload["itemList"])        # Total tax amount
	payload["totTaxblAmt"] = sum(item["vatTaxblAmt"] for item in payload["itemList"]) # Total taxable amount

	return payload