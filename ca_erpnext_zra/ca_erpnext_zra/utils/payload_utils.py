import frappe
from frappe.utils import now

from frappe.utils import now_datetime, getdate, cint, flt
from frappe.utils.password import get_decrypted_password
import re
from frappe.utils.data import flt
from datetime import datetime
from frappe.utils import cstr, get_datetime



from frappe.model.document import Document
from .tax_utils import calculate_tax

# from .id_utils import get_vsdc_id

from typing import Dict, Any




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
        "itemList": []
    }

    for item in sale_items:
        payload["itemList"].append({
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
            "exciseTxAmt": None
        })

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


def build_debit_note_payload(docname: str, settings_name: str = None) -> Dict[str, Any]:
    """
    Build a Debit Note payload for Smart Invoice (ZRA) from a Purchase Invoice/Debit Note.
    This logic assumes a single VAT bucket (A) and handles item-level tax breakdown.

    Args:
        docname (str): name of the Purchase Invoice or Debit Note in ERPNext
        settings_name (str, optional): Crystal ZRA Smart Invoice Settings record name.
                                       If None, the first record is fetched.
    Returns:
        dict: payload ready for submission to Smart Invoice API
    """
    # ------------------
    # 1. Fetch Documents and Settings
    # ------------------
    doc = frappe.get_doc("Purchase Invoice", docname)

    tpin = ""
    bhf_id = "000" # Default as per example
    if not settings_name:
        # Fetch the name of the first settings record if not provided
        settings_record = frappe.get_all(
            "Crystal ZRA Smart Invoice Settings",
            fields=["name"],
            limit=1
        )
        if settings_record:
            settings_name = settings_record[0]["name"]

    if settings_name:
        settings_doc = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
        # Assuming get_decrypted_password is available in the environment
        tpin = get_decrypted_password(
            "Crystal ZRA Smart Invoice Settings",
            settings_name,  # positional docname
            "tpin",         # fieldname
            raise_exception=False
        ) or ""
        bhf_id = cstr(getattr(settings_doc, "branch_id", "000")) or "000"

    user = frappe.session.user or "admin"

    # Totals (use document fields if available)
    tot_item_cnt = len(doc.items or [])

    # The doc totals are now explicitly ignored in favor of calculated ZRA totals
    # doc_base_net_total = _safe_float(getattr(doc, "base_net_total", 0))
    # doc_base_tax_total = _safe_float(getattr(doc, "base_tax_total", 0))
    # doc_base_grand_total = _safe_float(getattr(doc, "base_grand_total", 0))

    # Optional document-level dates
    # Ensure date fields (confirmation_date, posting_date) are passed to the fixed formatters
    cfm_dt = _fmt_datetime(getattr(doc, "confirmation_date", None) or getattr(doc, "posting_date", None))
    sales_dt = _fmt_date(getattr(doc, "posting_date", None))

    # Prepare fields that require specific validation (TPIN, LPO)
    cust_tpin_val = cstr(getattr(doc, "supplier_tpin", None) or getattr(doc, "customer_tpin", None))
    # Ensure custTpin is None if it's an empty string to avoid "Must be a valid TPIN" error
    safe_cust_tpin = cust_tpin_val if cust_tpin_val else None

    lpo_number_val = cstr(getattr(doc, "lpo_number", None))
    # Ensure lpoNumber is None if it doesn't meet the length requirement (9 to 20)
    safe_lpo_number = lpo_number_val if 9 <= len(lpo_number_val) <= 20 else None

   # Original Invoice Number must be provided for Debit Notes.
    # 1. Get the document name from custom field or standard 'return_against' field.
    org_invc_no_val = cstr(getattr(doc, "original_invoice_number", None))
    if not org_invc_no_val:
        org_invc_no_val = cstr(getattr(doc, "return_against", None))

    # 2. Extract the numeric suffix required by the ZRA API (Int64).
    extracted_numeric_suffix = None
    if org_invc_no_val and org_invc_no_val != "0":
        try:
            # Split by '-', take the last part (which is the serial number)
            # Example: "ACC-PINV-2025-00049" -> "00049"
            parts = org_invc_no_val.split('-')
            numeric_part = parts[-1]

            # Convert to integer to strip leading zeros (e.g., "00049" -> 49),
            # then back to string for the payload.
            # This is done to satisfy the API's Int64 requirement for the invoice number.
            extracted_numeric_suffix = cstr(int(numeric_part))
        except (ValueError, IndexError):
            # If conversion or splitting fails (e.g., non-standard doc name), use the full string.
            extracted_numeric_suffix = org_invc_no_val

    # 3. Final assignment: Ensure the value is None if it's still missing or "0"
    safe_org_invc_no = extracted_numeric_suffix if extracted_numeric_suffix and extracted_numeric_suffix != "0" else None


    # ------------------
    # 2. Base Payload Structure & Defaults
    # ------------------
    # Rates are read first so the item loop can use them for calculation
    rates = {
        "A": _safe_float(getattr(doc, "tax_rate_a", 16)),
        "B": _safe_float(getattr(doc, "tax_rate_b", 16)),
        "C1": _safe_float(getattr(doc, "tax_rate_c1", 0)),
        "C2": _safe_float(getattr(doc, "tax_rate_c2", 0)),
        "C3": _safe_float(getattr(doc, "tax_rate_c3", 0)),
        "D": _safe_float(getattr(doc, "tax_rate_d", 0)),
        "Rvat": _safe_float(getattr(doc, "tax_rate_rvat", 16)),
        "E": _safe_float(getattr(doc, "tax_rate_e", 0)),
        "F": _safe_float(getattr(doc, "tax_rate_f", 10)),
        "Ipl1": _safe_float(getattr(doc, "tax_rate_ipl1", 5)),
        "Ipl2": _safe_float(getattr(doc, "tax_rate_ipl2", 0)),
        "Tl": _safe_float(getattr(doc, "tax_rate_tl", 1.5)),
        "Ecm": _safe_float(getattr(doc, "tax_rate_ecm", 5)),
        "Exeeg": _safe_float(getattr(doc, "tax_rate_exeeg", 3)),
        "Tot": _safe_float(getattr(doc, "tax_rate_tot", 0)),
    }
    
    payload: Dict[str, Any] = {
        "tpin": tpin,
        "bhfId": bhf_id,
        "cisInvcNo": cstr(getattr(doc, "custom_cis_number", doc.name)),
        "custTpin": safe_cust_tpin,
        "custNm": cstr(getattr(doc, "supplier_name", None) or getattr(doc, "customer_name", None)),
        "salesTyCd": "N",  # default: Normal
        "rcptTyCd": "D",  # D = Debit Note
        "pmtTyCd": cstr(getattr(doc, "payment_type_code", "01")),
        "salesSttsCd": cstr(getattr(doc, "sales_status_code", "02")),
        "cfmDt": cfm_dt, # Uses the fixed 14-char format
        "salesDt": sales_dt, # Uses the fixed 8-char format
        "stockRlsDt": None,
        "cnclReqDt": None,
        "cnclDt": None,
        "rfdDt": None,
        "rfdRsnCd": None,
        
        "totItemCnt": tot_item_cnt,
        
        # Initialize tax buckets (Amounts and Taxable) and rates from the 'rates' dictionary
        "taxblAmtA": 0.0, "taxblAmtB": 0.0, "taxblAmtC1": 0.0, "taxblAmtC2": 0.0,
        "taxblAmtC3": 0.0, "taxblAmtD": 0.0, "taxblAmtRvat": 0.0, "taxblAmtE": 0.0,
        "taxblAmtF": 0.0, "taxblAmtIpl1": 0.0, "taxblAmtIpl2": 0.0, "taxblAmtTl": 0.0,
        "taxblAmtEcm": 0.0, "taxblAmtExeeg": 0.0, "taxblAmtTot": 0.0,

        "taxRtA": rates["A"], "taxRtB": rates["B"], "taxRtC1": rates["C1"], "taxRtC2": rates["C2"],
        "taxRtC3": rates["C3"], "taxRtD": rates["D"], "taxRtRvat": rates["Rvat"],
        "taxRtE": rates["E"], "taxRtF": rates["F"], "taxRtIpl1": rates["Ipl1"],
        "taxRtIpl2": rates["Ipl2"], "taxRtTl": rates["Tl"], "taxRtEcm": rates["Ecm"],
        "taxRtExeeg": rates["Exeeg"], "taxRtTot": rates["Tot"],
        
        "taxAmtA": 0.0, "taxAmtB": 0.0, "taxAmtC1": 0.0, "taxAmtC2": 0.0,
        "taxAmtC3": 0.0, "taxAmtD": 0.0, "taxAmtRvat": 0.0, "taxAmtE": 0.0,
        "taxAmtF": 0.0, "taxAmtIpl1": 0.0, "taxAmtIpl2": 0.0, "taxAmtTl": 0.0,
        "taxAmtEcm": 0.0, "taxAmtExeeg": 0.0, "taxAmtTot": 0.0,
        
        # Totals are initialized to zero and calculated accurately in step 5
        "totTaxblAmt": 0.0,
        "totTaxAmt": 0.0,
        "totAmt": 0.0, 
        
        "tlAmt": 0.0, # This field appears in the original list but is a tax type, keep as 0.0 init
        
        "cashDcRt": _safe_float(getattr(doc, "cash_discount_rate", 0)),
        "cashDcAmt": _safe_float(getattr(doc, "cash_discount_amount", 0)),
        "prchrAcptcYn": cstr(getattr(doc, "prchr_acptc_yn", "N")),
        "remark": cstr(getattr(doc, "remarks", "") or ""),
        "regrId": user,
        "regrNm": user,
        "modrId": user,
        "modrNm": user,
        "saleCtyCd": cstr(getattr(doc, "sale_city_code", "1")),
        "lpoNumber": safe_lpo_number,
        "currencyTyCd": cstr(getattr(doc, "currency", frappe.defaults.get_global_default("currency") or "ZMW")),
        "exchangeRt": cstr(_safe_float(getattr(doc, "exchange_rate", 1))),
        "destnCountryCd": cstr(getattr(doc, "destination_country_code", "") or ""),
        "dbtRsnCd": cstr(getattr(doc, "debit_reason_code", "03")),
        "invcAdjustReason": cstr(getattr(doc, "adjust_reason", "")),
        "itemList": [],
    }

    # Conditionally add orgInvcNo. ZRA API often fails if this mandatory field is 'null',
    # requiring it to be omitted if not present in ERPNext.
    if safe_org_invc_no:
        payload["orgInvcNo"] = safe_org_invc_no

    # ------------------
    # 3. Per-item mapping & Totals Accumulation
    # ------------------
        # ------------------
    # 3. Per-item mapping & Totals Accumulation
    # ------------------
    for item_seq, itm in enumerate(doc.items, 1):
        item_code = cstr(itm.get("item_code"))
        item_name = cstr(itm.get("item_name"))
        item_cls = cstr(
            getattr(itm, "custom_item_classification", None)
            or frappe.db.get_value("Item", item_code, "custom_smart_item_classification_code")
            or "50102517"
        )

        qty = abs(_safe_float(itm.get("qty", 1)))
        rate = abs(_safe_float(itm.get("rate", itm.get("base_rate", 0))))
        dc_amt = abs(_safe_float(itm.get("discount_amount", 0)))
        dc_rt = abs(_safe_float(itm.get("discount_percentage", 0)))

        # Determine tax category and rate
        vat_cat_cd = cstr(getattr(itm, "vat_category", "A") or "A")
        tax_rate = rates.get(vat_cat_cd, 0.0)

        # === Calculate amounts exactly like in invoice builder ===
        sply_amt = round(rate * qty, 2)                    # Supply amount before tax
        vat_rate = round(rate * tax_rate / 100, 4)         # VAT per unit
        vat_amt = round(sply_amt * tax_rate / 100, 2)      # Total VAT on line
        sply_rate = round(rate + vat_rate, 4)              # Rate including VAT
        tot_amt = round(sply_amt - dc_amt + vat_amt, 2)    # Supply - discount + VAT
        tl_amt = tot_amt                                   # For compatibility

        # === Update tax bucket totals ===
        if vat_cat_cd in rates:
            taxbl_key = f"taxblAmt{vat_cat_cd}"
            taxamt_key = f"taxAmt{vat_cat_cd}"
            taxrt_key = f"taxRt{vat_cat_cd}"
            payload[taxbl_key] = round(payload.get(taxbl_key, 0) + sply_amt, 4)
            payload[taxamt_key] = round(payload.get(taxamt_key, 0) + vat_amt, 2)
            payload[taxrt_key] = tax_rate

        # === Item payload ===
        item_payload = {
            "itemSeq": item_seq,
            "itemCd": item_code,
            "itemNm": item_name,
            "itemClsCd": item_cls,
            "qty": qty,
            "qtyUnitCd": cstr(getattr(itm, "uom", getattr(itm, "stock_uom", "EA"))),
            "prc": sply_rate,
            "splyAmt": tl_amt,
            "vatAmt": vat_amt,
            "tlAmt": 0,
            "totAmt": tot_amt,
            "vatTaxblAmt": sply_amt,
            "tlTaxblAmt": sply_amt,
            "pkg": abs(itm.get("package_qty") or 1),
            "pkgUnitCd": cstr(getattr(itm, "package_unit", "EA")),
            "dcAmt": dc_amt,
            "dcRt": dc_rt,
            "bcd": cstr(getattr(itm, "barcode", "") or ""),
            "vatCatCd": vat_cat_cd,
        }
        payload["itemList"].append(item_payload)


    # ------------------
    # 5. Final Totals Update (Aggregate all buckets)
    # ------------------
    total_taxable_amount = 0.0
    total_tax_amount = 0.0
    total_items_amount = 0.0 # Calculate this from the item list's totAmt

    # Iterate through all tax bucket keys to compute final totals
    for key in ["A", "B", "C1", "C2", "C3", "D", "Rvat", "E", "F", "Ipl1", "Ipl2", "Tl", "Ecm", "Exeeg"]:
        # Round the accumulated bucket values before final summation
        # This double-rounding is okay since the accumulation used item-level rounded values.
        payload[f"taxblAmt{key}"] = round(payload.get(f"taxblAmt{key}", 0.0), 4)
        payload[f"taxAmt{key}"] = round(payload.get(f"taxAmt{key}", 0.0), 2)

        total_taxable_amount += payload[f"taxblAmt{key}"]
        total_tax_amount += payload[f"taxAmt{key}"]
        
    # Get the sum of all item total amounts
    total_items_amount = sum(i.get("totAmt", 0) for i in payload["itemList"])

    # Update final totals in the payload (using calculated sums)
    payload["totTaxblAmt"] = round(total_taxable_amount, 4)
    payload["totTaxAmt"] = round(total_tax_amount, 2)

    # Total Amount = (Sum of Item Totals) - Cash Discount Amount
    computed_tot_amt = round(total_items_amount - payload.get("cashDcAmt", 0), 2)
    payload["totAmt"] = computed_tot_amt

    # IMPORTANT: Wrap the entire transaction payload under the 'debitNoteTxn' key
    # as required by the API.
    return payload


@frappe.whitelist()
def build_purchase_payload(docname: str, settings_name: str) -> dict:
 
    # Fetch documents
    doc = frappe.get_doc("Purchase Invoice", docname)
            # Fetch first settings record
    settings = frappe.get_all(
        "Crystal ZRA Smart Invoice Settings",
        fields=["name"]
    )

  

    tpin = ""
    if settings:
        settings_name = settings[0]["name"]
        tpin = get_decrypted_password(
            "Crystal ZRA Smart Invoice Settings",
            settings_name,        # positional docname
            "tpin",               # fieldname
            raise_exception=False
        ) or ""

    # --- Helper: safely get numeric supplier invoice number ---
    def get_supplier_invoice_number(value):
        try:
            # If doc.name ends like "ACC-PINV-2025-00002" → returns 2
            return int(str(value).split("-")[-1])
        except Exception:
            return 0

    payload = {
        "tpin":tpin,
        "bhfId": getattr(settings, "branch_id", "000"),
        "cisInvcNo": f"cis_{doc.name}",
        "orgInvcNo": 0,
        "spplrTpin": getattr(doc, "supplier_tpin", None),
        "spplrBhfId": getattr(doc, "supplier_branch_id", "000"),
        "spplrNm": doc.supplier_name,
        "spplrInvcNo": get_supplier_invoice_number(doc.name),
        "regTyCd": "M",       # M = Manual
        "pchsTyCd": "N",      # N = Normal Purchase
        "rcptTyCd": "P",      # P = Purchase
        "pmtTyCd": "01",      # 01 = Cash
        "pchsSttsCd": "02",   # 02 = Confirmed
        "cfmDt": now_datetime().strftime("%Y%m%d%H%M%S"),
        "pchsDt": now_datetime().strftime("%Y%m%d"),
        "cnclReqDt": "",
        "cnclDt": "",
        "totItemCnt": len(doc.items),
        "totTaxblAmt": round(sum(float(i.base_net_amount) for i in doc.items), 4),
        "totTaxAmt": round(sum(float(getattr(i, "item_tax_amount", 0)) for i in doc.items), 4),
        "totAmt": round(float(doc.base_grand_total), 2),
        "remark": doc.remarks or "No Remarks",
        "regrNm": frappe.session.user,
        "regrId": frappe.session.user,
        "modrNm": frappe.session.user,
        "modrId": frappe.session.user,
        "itemList": [],
    }

    # --- Build item list ---
    for idx, item in enumerate(doc.items, start=1):
   # Fetch custom codes
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


def generate_vsdc_item_payload(item_name: str) -> dict:
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
    settings = frappe.get_all(
        "Crystal ZRA Smart Invoice Settings",
        fields=["name"]
    )

    tpin = ""
    if settings:
        settings_name = settings[0]["name"]
        tpin = get_decrypted_password(
            "Crystal ZRA Smart Invoice Settings",
            settings_name,     
            "tpin",               
            raise_exception=False
        ) or ""
    # --- Get BhfId from Settings ---
    # bhf_id = frappe.db.get_single_value("Crystal ZRA Smart Invoice Settings", "branch_id") or "000"

    payload = {
        "tpin": tpin,
        "bhfid":"000",
        "itemCd": item.custom_smart_item_code, #Generate a custom smart_item_code
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
        "rentalYn": "Y" if item.get("custom_smart_rental_income_applicable") else "N",        "addInfo": item.get("additional_info") or None,
        "sftyQty": float(item.get("safety_stock") or 0),
        "isrcAplcbYn": "Y" if item.get("custom_smart_insurance_applicable") else "N",        "useYn": "Y" if item.disabled == 0 else "N",
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
    settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
    tpin = get_decrypted_password("Crystal ZRA Smart Invoice Settings", settings_name, "tpin") or ""
    bhf_id = "000"

    # Dates
    sales_dt = datetime.strptime(str(invoice.posting_date), "%Y-%m-%d").strftime("%Y%m%d")
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")

    reference_number = invoice.name
    customer = frappe.get_doc("Customer", invoice.customer)

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

    payload = {
        "tpin": tpin,
        "bhfId": bhf_id,
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

    # Initialize tax category fields
    for _, (taxbl, taxamt, taxrt) in tax_field_map.items():
        payload[taxbl] = fmt4(0)
        payload[taxamt] = fmt4(0)
        payload[taxrt] = 0

    # Line items
    for idx, item in enumerate(invoice.items, start=1):
        # Fetch custom codes
        pkg_code = frappe.db.get_value("Item", item.item_code, "custom_smart_packaging_unit") or "EA"
        class_code = frappe.db.get_value("Item", item.item_code, "custom_smart_item_classification_code") or "00000000"
        uom_code = frappe.db.get_value("Item", item.item_code, "custom_smart_quantity_unit") or "EA"

        qty = fmt4(item.qty)
        rate = fmt4(item.rate)

        # Supply amount = net amount before tax
        # sply_amt = fmt4(item.net_amount)

        sply_amt = fmt4(rate * qty)
        

        # Discount
        dc_amt = fmt4(item.get("discount_amount") or 0)
        dc_rt = fmt4(item.get("discount_percentage") or 0)

        # Tax rate
        tax_rate = float(item.get("custom_tax_rate") or 0)
        vat_rate = fmt4(rate * tax_rate / 100)
        vat_amt = fmt4(sply_amt * tax_rate / 100)

        # Totals
        tot_amt = fmt4(sply_amt - dc_amt + vat_amt) 
        tl_amt = tot_amt 

        sply_rate = fmt4(rate + vat_rate)
        # tl_amt = fmt4(sply_amt + vat_amt)   # line total including VAT
        # tot_amt = fmt4(sply_amt - dc_amt + vat_amt)  # supply - discount + taxes

        # Update tax category totals
        vat_cat = item.get("custom_taxation_type") or "A"
        if vat_cat in tax_field_map:
            taxbl, taxamt, taxrt = tax_field_map[vat_cat]
            
            payload[taxbl] = fmt4(payload[taxbl] + sply_amt)
            payload[taxamt] = fmt4(payload[taxamt] + vat_amt)
            payload[taxrt] = int(round(tax_rate))

        # Item block
        payload["itemList"].append({
            "itemSeq": idx,
            "itemCd": item.item_code,
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
        })

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

    settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
    original_invoice = frappe.get_doc("Sales Invoice", doc.return_against)
    customer = frappe.get_doc("Customer", doc.customer)
    org_invc_no = original_invoice.get("custom_scu_invoice_number")

    tpin = get_decrypted_password(
        "Crystal ZRA Smart Invoice Settings",
        settings.name,
        "tpin",
        raise_exception=False
    ) or ""

    bhf_id =  "000"

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
        "bhfId": bhf_id,
        "orgInvcNo": int(original_invoice.custom_current_receipt_number),
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
        class_code = frappe.db.get_value("Item", item.item_code, "custom_smart_item_classification_code") or "00000000"
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

       
        vat_cat = get_vat_category(item)

        # Update tax fields by category
        if vat_cat in tax_field_map:
            taxbl, taxamt, taxrt = tax_field_map[vat_cat]
            payload[taxbl] = fmt4(payload[taxbl] + sply_amt)
            payload[taxamt] = fmt4(payload[taxamt] + vat_amt)
            payload[taxrt] = int(round(tax_rate))

        payload["itemList"].append({
            "itemSeq": idx,
            "itemCd": item.item_code,
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
        })

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
            tax_rate = list(item.custom_tax_rate.values())[0]
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
            item_doc = frappe.db.get_value(
                "Item",
                item_code,
                ["item_name", "custom_smart_item_classification_code", "valuation_rate"],
                as_dict=True
            ) or {}
            class_code = item_doc.get("custom_smart_item_classification_code") 
            item_name = item_doc.get("item_name")
            price = float(item.get("prc") or 0)
            qty = float(item.get("qty") or 1)
            tax_rate = 0.16  # Get this dynamically based on configuration
            tax_amt = round(price * qty * tax_rate / (1 + tax_rate), 2)
            taxable_amt = round(price * qty - tax_amt, 2)

            item_list.append({
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
            })

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
                current_qty = frappe.db.get_value(
                    "Bin",
                    {"item_code": item_code, "warehouse": warehouse},
                    "actual_qty"
                ) or 0
            else:
                # Aggregate quantity across all warehouses
                current_qty = frappe.db.get_all(
                    "Bin",
                    filters={"item_code": item_code},
                    fields=["sum(actual_qty) as qty"]
                )[0].qty or 0

            # Subtract the sold quantity from current stock
            sold_qty = float(i.get("qty", 0))
            remaining_qty = float(current_qty) - sold_qty

            stock_item_list.append({
                "itemCd": item_code,
                "rsdQty": remaining_qty,
            })

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

    company_tpin = frappe.db.get_value("Crystal ZRA Smart Invoice Settings", {"company": doc.company}, "tpin") or ""
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

        item_list.append({
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
        })

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
        "ocrnDt": doc.posting_date.strftime("%Y%m%d") if getattr(doc, "posting_date", None) else now().split(" ")[0],
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
        item_list.append({
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
        })
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
    prefix_parts = [
        doc.get("custom_smart_packaging_unit") or "",
        doc.get("custom_smart_quantity_unit") or "",
        doc.get("custom_smart_item_type") or "",
        doc.get("custom_smart_item_classification_code") or "",
       
    ]
    new_prefix = "".join(prefix_parts)
    if doc.get("custom_smart_item_code"):
        existing_suffix = doc.custom_smart_item_code[-7:]
    else:
        # Find last code under same classification to increment suffix
        last_code = frappe.db.sql(
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

        last_code = last_code[0][0] if last_code else None
        if last_code:
            try:
                last_suffix = int(last_code[-7:])
                existing_suffix = str(last_suffix + 1).zfill(7)
            except ValueError:
                existing_suffix = "0000001"
        else:
            existing_suffix = "0000001"

    new_code = f"{new_prefix}{existing_suffix}"

    # Save it back to the Item if needed
    doc.db_set("custom_smart_item_code", new_code, update_modified=False)
    frappe.logger().info(f"[SMART] Generated Smart Code for {doc.name}: {new_code}")

    return new_code
