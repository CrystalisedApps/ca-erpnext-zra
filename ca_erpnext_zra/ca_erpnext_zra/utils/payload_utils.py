import frappe
from frappe.utils import now

from frappe.utils import now_datetime, getdate, cint, flt
from frappe.utils.password import get_decrypted_password
import re
from frappe.utils.data import flt
from datetime import datetime




from frappe.model.document import Document
from .tax_utils import calculate_tax

# from .id_utils import get_vsdc_id

from typing import Dict, Any




def map_zra_purchase_to_payload(purchase_data: dict, company_tpin: str) -> dict:
    """
    Map fetched ZRA purchase data to Smart 'savePurchase' payload format.
    """

    sale_items = purchase_data.get("itemList", [])

    payload = {
        "tpin": company_tpin,  # Your own TPIN
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



def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _fmt_datetime(dt) -> str:
    """Return YYYYMMDDHHMMSS (cfmDt style)."""
    if not dt:
        return now_datetime().strftime("%Y%m%d%H%M%S")
    if isinstance(dt, str):
        # assume already formatted
        return dt
    return dt.strftime("%Y%m%d%H%M%S")


def _fmt_date(d) -> str:
    """Return YYYYMMDD (pchsDt / salesDt style)."""
    if not d:
        return now_datetime().strftime("%Y%m%d")
    if isinstance(d, str):
        return d
    return d.strftime("%Y%m%d")


def build_debit_note_payload(docname: str, settings_name: str) -> Dict[str, Any]:
    """
    Build a Debit Note payload for Smart Invoice (ZRA) from a Purchase Invoice / Credit Note doc.

    Args:
        docname (str): name of the Purchase Invoice (or Debit Note) in ERPNext
        settings_name (str): Crystal ZRA Smart Invoice Settings record name

    Returns:
        dict: payload ready for submission to Smart Invoice API
    """
    # Fetch documents
    doc = frappe.get_doc("Purchase Invoice", docname)
    # settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)

    # Top-level values & defaults
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
    bhf_id = getattr(settings, "branch_id", "000") or "000"
    user = frappe.session.user or "admin"

    # Totals (attempt to use doc fields; fallback to computed sums)
    tot_item_cnt = len(doc.items or [])
    tot_taxbl_amt = _safe_float(getattr(doc, "base_net_total", None)) or sum(
        (_safe_float(i.base_net_amount) for i in doc.items), 0.0
    )
    tot_tax_amt = _safe_float(getattr(doc, "base_tax_total", None)) or sum(
        (_safe_float(i.item_tax_amount or 0) for i in doc.items), 0.0
    )
    tot_amt = _safe_float(getattr(doc, "base_grand_total", None)) or sum(
        (_safe_float(i.base_amount) for i in doc.items), 0.0
    )

    # Optional document-level dates
    cfm_dt = _fmt_datetime(getattr(doc, "confirmation_date", None) or getattr(doc, "posting_date", None))
    sales_dt = _fmt_date(getattr(doc, "posting_date", None))

    # Base structure
    payload: Dict[str, Any] = {
        "tpin": tpin,
        "bhfId": bhf_id,
        "orgInvcNo": getattr(doc, "original_invoice_number", 0) or 0,
        "cisInvcNo": getattr(doc, "custom_cis_number", doc.name),
        "custTpin": getattr(doc, "customer_tpin", None),
        "custNm": getattr(doc, "supplier_name", None) or getattr(doc, "customer_name", None),
        "salesTyCd": "N",  # default: Normal (adjust where required)
        "rcptTyCd": "D",  # D = Debit Note / Receipt type
        "pmtTyCd": getattr(doc, "payment_type_code", "01"),
        "salesSttsCd": getattr(doc, "sales_status_code", "02"),
        "cfmDt": cfm_dt,
        "salesDt": sales_dt,
        "stockRlsDt": None,
        "cnclReqDt": None,
        "cnclDt": None,
        "rfdDt": None,
        "rfdRsnCd": None,
        # Tax buckets — try to copy common fields; keep all buckets present with defaults
        "totItemCnt": tot_item_cnt,
        "taxblAmtA": 0.0,
        "taxblAmtB": 0.0,
        "taxblAmtC1": 0.0,
        "taxblAmtC2": 0.0,
        "taxblAmtC3": 0.0,
        "taxblAmtD": 0.0,
        "taxblAmtRvat": 0.0,
        "taxblAmtE": 0.0,
        "taxblAmtF": 0.0,
        "taxblAmtIpl1": 0.0,
        "taxblAmtIpl2": 0.0,
        "taxblAmtTl": 0.0,
        "taxblAmtEcm": 0.0,
        "taxblAmtExeeg": 0.0,
        "taxblAmtTot": 0.0,
        # Tax rates (defaults — adjust mapping logic if you have proper rates)
        "taxRtA": getattr(doc, "tax_rate_a", 16),
        "taxRtB": getattr(doc, "tax_rate_b", 0),
        "taxRtC1": getattr(doc, "tax_rate_c1", 0),
        "taxRtC2": getattr(doc, "tax_rate_c2", 0),
        "taxRtC3": getattr(doc, "tax_rate_c3", 0),
        "taxRtD": getattr(doc, "tax_rate_d", 0),
        "tlAmt": 0.0,
        "taxRtRvat": getattr(doc, "tax_rate_rvat", 16),
        "taxRtE": 0,
        "taxRtF": 0,
        "taxRtIpl1": 0,
        "taxRtIpl2": 0,
        "taxRtTl": 0,
        "taxRtEcm": 0,
        "taxRtExeeg": 0,
        "taxRtTot": 0,
        # Tax amounts
        "taxAmtA": 0.0,
        "taxAmtB": 0.0,
        "taxAmtC1": 0.0,
        "taxAmtC2": 0.0,
        "taxAmtC3": 0.0,
        "taxAmtD": 0.0,
        "taxAmtRvat": 0.0,
        "taxAmtE": 0.0,
        "taxAmtF": 0.0,
        "taxAmtIpl1": 0.0,
        "taxAmtIpl2": 0.0,
        "taxAmtTl": 0.0,
        "taxAmtEcm": 0.0,
        "taxAmtExeeg": 0.0,
        "taxAmtTot": 0.0,
        # Totals
        "totTaxblAmt": round(tot_taxbl_amt, 4),
        "totTaxAmt": round(tot_tax_amt, 2),
        "cashDcRt": getattr(doc, "cash_discount_rate", 0),
        "cashDcAmt": getattr(doc, "cash_discount_amount", 0),
        "totAmt": round(tot_amt, 2),
        "prchrAcptcYn": getattr(doc, "prchr_acptc_yn", "N"),
        "remark": getattr(doc, "remarks", "") or "",
        "regrId": user,
        "regrNm": user,
        "modrId": user,
        "modrNm": user,
        "saleCtyCd": getattr(doc, "sale_city_code", "1"),
        "lpoNumber": getattr(doc, "lpo_number", None),
        "currencyTyCd": getattr(doc, "currency", frappe.defaults.get_global_default("currency") or "ZMW"),
        "exchangeRt": str(getattr(doc, "exchange_rate", 1)),
        "destnCountryCd": getattr(doc, "destination_country_code", "") or "",
        "dbtRsnCd": getattr(doc, "debit_reason_code", "03"),
        "invcAdjustReason": getattr(doc, "adjust_reason", ""),
        "itemList": [],
    }

    # Per-item mapping — iterate items and compute taxables/taxes as needed
    item_seq = 1
    running_tot_taxbl = 0.0
    running_tot_tax = 0.0
    for itm in doc.items:
        # attempt to pull classification and mapping from Item master or line fields
        item_code = getattr(itm, "item_code", itm.get("item_code", None)) if hasattr(itm, "item_code") else itm.get("item_code")
        item_name = getattr(itm, "item_name", itm.get("item_name", None)) if hasattr(itm, "item_name") else itm.get("item_name")
        item_cls = getattr(itm, "custom_item_classification", None) or frappe.db.get_value("Item", item_code, "custom_smart_item_classification_code") or "50102517"

        qty = _safe_float(getattr(itm, "qty", itm.get("qty", 1)))
        prc = _safe_float(getattr(itm, "rate", getattr(itm, "base_rate", itm.get("prc", 0))))
        sply_amt = round(prc * qty, 2)

        # discount / dc
        dc_rt = _safe_float(getattr(itm, "discount_percentage", itm.get("dcRt", 0)))
        dc_amt = _safe_float(getattr(itm, "discount_amount", itm.get("dcAmt", 0)))

        # Determine VATable / IPL / other breakdown — try to use line-level tax info when present
        vat_taxable = 0.0
        vat_amt = 0.0
        ipl_taxable = 0.0
        ipl_amt = 0.0

        # If line has item_tax_amount or taxes table, use that to compute
        if getattr(itm, "item_tax_amount", None) is not None:
            vat_amt = _safe_float(itm.item_tax_amount)
            # Back-calc taxable if tax rate known (assume 16% if not)
            assumed_rate = getattr(itm, "tax_rate", 16) or 16
            vat_taxable = round((sply_amt - dc_amt) - (vat_amt / (assumed_rate / 100 + 1) * 0), 4)  # keep simple
            # Simpler approach: set taxable = sply_amt - dc_amt when API expects totals
            vat_taxable = round(sply_amt - dc_amt, 4)
        else:
            # no tax info: assume taxable = sply_amt - dc_amt and tax rate from doc/settings
            vat_taxable = round(sply_amt - dc_amt, 4)
            vat_amt = round(vat_taxable * (getattr(itm, "tax_rate", 16) or 16) / 100, 2)

        running_tot_taxbl += vat_taxable
        running_tot_tax += vat_amt

        item_payload = {
            "itemSeq": item_seq,
            "itemCd": item_code,
            "itemClsCd": item_cls,
            "itemNm": item_name,
            "bcd": getattr(itm, "barcode", "") or "",
            "pkgUnitCd": getattr(itm, "package_unit", "BA"),
            "pkg": _safe_float(getattr(itm, "package_qty", 0)),
            "qtyUnitCd": getattr(itm, "uom", getattr(itm, "stock_uom", "BE")),
            "qty": qty,
            "prc": prc,
            "splyAmt": sply_amt,
            "dcRt": dc_rt,
            "dcAmt": dc_amt,
            "isrccCd": getattr(itm, "isrc_code", "") or "",
            "isrccNm": getattr(itm, "isrc_name", "") or "",
            "isrcRt": 0,
            "isrcAmt": 0,
            "vatCatCd": getattr(itm, "vat_category", None),
            "exciseTxCatCd": None,
            "tlCatCd": None,
            "iplCatCd": getattr(itm, "ipl_category", None),
            "vatTaxblAmt": round(vat_taxable, 4),
            "vatAmt": round(vat_amt, 2),
            "exciseTaxblAmt": 0,
            "tlTaxblAmt": 0,
            "iplTaxblAmt": round(ipl_taxable, 4),
            "iplAmt": round(ipl_amt, 2),
            "totAmt": round(sply_amt - dc_amt, 2),
        }

        payload["itemList"].append(item_payload)
        item_seq += 1

    # Update totals from item loop if we computed them
    payload["taxblAmtA"] = round(running_tot_taxbl, 4)
    payload["taxAmtA"] = round(running_tot_tax, 2)
    payload["totTaxblAmt"] = round(running_tot_taxbl, 4)
    payload["totTaxAmt"] = round(running_tot_tax, 2)
    payload["totItemCnt"] = len(payload["itemList"])
    # totAmt already set above but ensure it's consistent with sum of item totAmt + adjustments
    computed_tot_amt = round(sum(i.get("totAmt", 0) for i in payload["itemList"]) - payload.get("cashDcAmt", 0), 2)
    payload["totAmt"] = payload.get("totAmt") or computed_tot_amt

    return payload



@frappe.whitelist()
def build_purchase_payload(docname: str, settings_name: str) -> dict:
    """
    Dynamically build a valid Purchase payload for ZRA Smart Invoice (VSDC).

    Args:
        docname (str): Purchase Invoice document name
        settings_name (str): Crystal ZRA Smart Invoice Settings record name

    Returns:
        dict: Formatted payload ready for submission to ZRA API
    """

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
    """
    Generate Crystal VSDC Item payload from ERPNext Item doc.
    Assumes Item has custom fields linked to 'Crystallised Smart' doctypes.
    """

    item = frappe.get_doc("Item", item_name)

    def get_code(fieldname: str) -> str | None:
        """Fetch correct code field from linked Crystallised Smart doctypes."""
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
            settings_name,        # positional docname
            "tpin",               # fieldname
            raise_exception=False
        ) or ""
    # --- Get BhfId from Settings ---
    # bhf_id = frappe.db.get_single_value("Crystal ZRA Smart Invoice Settings", "branch_id") or "000"

    payload = {
        "tpin": tpin,
        "bhfid":"000",
        "itemCd": item.item_code,
        "itemClsCd": get_code("custom_smart_item_classification_code"),   # Link → Crystallised Smart Item Type
        "itemTyCd": item.custom_smart_item_type,              # Link → Crystallised Smart Item Type
        "itemNm": item.item_name,
        "itemStdNm": item.item_name,  # assuming same as itemNm
        "orgnNatCd": get_code("custom_smart_country_of_origin_"),          # Link → Crystallised Smart Countries
        "pkgUnitCd": get_code("custom_smart_packaging_unit"),        # Link → Crystallised Smart Packing Unit
        "qtyUnitCd": get_code("custom_smart_quantity_unit"),         # Link → Crystallised Smart Quantity Unit
        "vatCatCd": get_code("custom_vat_category_code"),           # Link → Crystallised Smart VAT Type
        "iplCatCd": get_code("custom_smart_insurance_premium_levy"),           # Link → Crystallised Smart IPL Registration Status
        "tlCatCd": get_code("custom_smart_tourism_levy"),          # Link → Crystallised Smart Tourism Levy
        "exciseTxCatCd": get_code("custom_smart_excise_duties_"),    # Link → Crystallised Smart Excise Duties
        "btchNo": item.get("batch_number") or None,
        "bcd": item.get("barcode") or None,
        "dftPrc": float(item.standard_rate),
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
    """Format to 4 decimal places as float."""
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

        rrp = abs(max(tot_amt, flt(item.get("custom_recommended_retail_price") or 0)))
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




def build_stock_payload(tpin, bhf_id, user, stock_items, route_key=None):
    """Builds payload for SaveStockItems or SaveStockMaster depending on route_key."""

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
            item_name = item.get("itemNm") 
            price = float(item.get("prc"))
            qty = float(item.get("qty") or 1)
            tax_rate = 0.16
            tax_amt = round(price * qty * tax_rate / (1 + tax_rate), 2)
            taxable_amt = round(price * qty - tax_amt, 2)
            # frappe.throw(str(item))
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
        # frappe.throw(str(payload))
    # SaveStockMaster — stock update
    else:
        payload = {
            "tpin": tpin,
            "bhfId": bhf_id,
            "regrId": user,
            "regrNm": user,
            "modrNm": user,
            "modrId": user,
            "stockItemList": [
                {
                    "itemCd": i.get("itemCd"),
                    "rsdQty": float(i.get("rsdQty") or i.get("qty") or 0)
                }
                for i in stock_items if i.get("itemCd")
            ],
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







# def build_stock_master_payload(settings_name, item_codes, warehouse=None):
#     """
#     Build payload for SaveStockMaster (stock balance sync)
#     """
#     settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
#     tpin = get_decrypted_password("Crystal ZRA Smart Invoice Settings", settings.name, "tpin", raise_exception=False) or ""
#     bhf = getattr(settings, "bhfid", "000") or "000"

#     stock_list = []
#     for code in item_codes:
#         qty = 0
#         if warehouse:
#             qty = flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "actual_qty") or 0)
#         else:
#             qty = flt(frappe.db.sql("""SELECT SUM(actual_qty) FROM `tabBin` WHERE item_code=%s""", code)[0][0] or 0)

#         stock_list.append({
#             "itemCd": code,
#             "rsdQty": qty
#         })

#     payload = {
#         "tpin": tpin,
#         "bhfId": bhf,
#         "regrId": frappe.session.user,
#         "regrNm": frappe.utils.get_fullname(frappe.session.user),
#         "modrNm": frappe.utils.get_fullname(frappe.session.user),
#         "modrId": frappe.session.user,
#         "stockItemList": stock_list
#     }

#     return payload
# def build_stock_payload(tpin: str, bhf_id: str, user: str, stock_items: list):
#     return {
#         "tpin": tpin,
#         "bhfId": bhf_id,
#         "regrId": user,
#         "regrNm": user,
#         "modrNm": user,
#         "modrId": user,
#         "stockItemList": [
#             {"itemCd": d.get("item_code"), "rsdQty": float(d.get("qty", 0))}
#             for d in stock_items
#         ],
#     }
