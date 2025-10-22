import frappe
from frappe.utils import now_datetime, getdate, cint, flt
from frappe.utils.password import get_decrypted_password
import re
from frappe.utils.data import flt
from datetime import datetime
from frappe.utils import cint

from frappe import _dict, get_doc, get_value
from datetime import datetime

from frappe.model.document import Document
from .tax_utils import calculate_tax

# from .id_utils import get_vsdc_id




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
        "dftPrc": float(item.custom_recommended_retail_price) if item.custom_recommended_retail_price else 0,
        "manufacturerTpin": item.get("custom_manufacture_tpin") or None,
        "manufacturerItemCd": item.get("custom_manufacturer_item_code") or None,
        "rrp": float(item.get("standard_rate") or 0),
        "svcChargeYn": "Y" if item.get("is_service_charge_applicable") else "N",
        "rentalYn": "Y" if item.get("custom_smart_rental_income_applicable") else "N",        "addInfo": item.get("additional_info") or None,
        "sftyQty": float(item.get("custom_smartsafety_stock") or 0),
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
            "prc": tl_amt,
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


def build_sales_payload(sales_invoice_name, company_tpin, user="Admin"):
    """Builds ZRA Smart Invoice payload from Sales Invoice."""
    inv = frappe.get_doc("Sales Invoice", sales_invoice_name)
    item_list = []

    for i, item in enumerate(inv.items, start=1):
        item_doc = frappe.get_doc("Item", item.item_code)
        class_code = getattr(item_doc, "custom_class_code", None) or "50102517"
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




# def build_stock_items_payload(doc, settings_name, for_return=False):
#     """
#     Build payload for SaveStockItems (stock movement after invoice or return)
#     """

#     settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
#     tpin = get_decrypted_password("Crystal ZRA Smart Invoice Settings", settings.name, "tpin", raise_exception=False) or ""
#     bhf = getattr(settings, "branch_id", "000") or "000"

#     ocrn_dt = getdate(doc.posting_date).strftime("%Y%m%d")

#     total_taxable = total_vat = total_amount = 0
#     items = []

#     for idx, row in enumerate(doc.items, start=1):
#         qty = flt(row.qty)
#         if not for_return:  # Sales (stock out)
#             qty *= -1

#         taxable = flt(row.net_amount)
#         vat = flt(getattr(row, "custom_vat_amount", 0))
#         total = taxable + vat

#         total_taxable += taxable
#         total_vat += vat
#         total_amount += total

#         items.append({
#             "itemSeq": idx,
#             "itemCd": row.item_code,
#             "itemClsCd": frappe.db.get_value("Item", row.item_code, "custom_smart_item_classification_code") or "00000000",
#             "itemNm": row.item_name,
#             "pkgUnitCd": frappe.db.get_value("Item", row.item_code, "custom_smart_packaging_unit") or "EA",
#             "qtyUnitCd": frappe.db.get_value("Item", row.item_code, "custom_smart_quantity_unit") or "EA",
#             "qty": qty,
#             "prc": flt(row.rate, 2),
#             "splyAmt": flt(row.amount, 2),
#             "taxblAmt": flt(taxable, 2),
#             "vatCatCd": getattr(row, "custom_taxation_type", "A"),
#             "taxAmt": flt(vat, 2),
#             "totAmt": flt(total, 2)
#         })

#     payload = {
#         "tpin": tpin,
#         "bhfId": bhf,
#         "sarNo": cint(doc.name.split('-')[-1]) if '-' in doc.name else 1,
#         "orgSarNo": 0,
#         "regTyCd": "M",
#         "custTpin": getattr(doc, "customer_tax_id", None),
#         "custNm": getattr(doc, "customer_name", None),
#         "custBhfId": None,
#         "sarTyCd": "02",  # Transaction type code
#         "ocrnDt": ocrn_dt,
#         "totItemCnt": len(items),
#         "totTaxblAmt": round(total_taxable, 5),
#         "totTaxAmt": round(total_vat, 5),
#         "totAmt": round(total_amount, 2),
#         "remark": getattr(doc, "remarks", None),
#         "regrId": frappe.session.user,
#         "regrNm": frappe.utils.get_fullname(frappe.session.user),
#         "modrNm": frappe.utils.get_fullname(frappe.session.user),
#         "modrId": frappe.session.user,
#         "itemList": items
#     }

#     return payload


# def build_stock_master_payload(settings_name, item_codes, warehouse=None):
#     """
#     Build payload for SaveStockMaster (stock balance sync)
#     """
#     settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
#     tpin = get_decrypted_password("Crystal ZRA Smart Invoice Settings", settings.name, "tpin", raise_exception=False) or ""
#     bhf = getattr(settings, "branch_id", "000") or "000"

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
