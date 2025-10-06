
from datetime import datetime
import frappe

from frappe.utils.password import get_decrypted_password
from frappe.utils.data import flt
from datetime import datetime

from frappe import _dict, get_doc, get_value
from datetime import datetime
from frappe.utils import now_datetime, nowdate
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
        "rrp": float(item.get("custom_recommended_retail_price") or 0),
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
    bhf_id = settings.get("branch_id") or "000"

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
        sply_amt = fmt4(item.net_amount)

        # Discount
        dc_amt = fmt4(item.get("discount_amount") or 0)
        dc_rt = fmt4(item.get("discount_percentage") or 0)

        # Tax rate
        tax_rate = float(item.get("custom_tax_rate") or 0)
        vat_amt = item.get("custom_vat_amount")

        # Totals
        
        tot_amt = fmt4(sply_amt + vat_amt) 
        tl_amt = tot_amt 
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
            "prc": tl_amt,
            "splyAmt": tot_amt,
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






TAX_CATEGORY_MAP = {
    "A": {"tax_rate": 16, "taxbl_key": "taxblAmtA", "tax_key": "taxAmtA", "rate_key": "taxRtA"},
    "B": {"tax_rate": 16, "taxbl_key": "taxblAmtB", "tax_key": "taxAmtB", "rate_key": "taxRtB"},
    "IPL2": {"tax_rate": 5, "taxbl_key": "taxblAmtIpl2", "tax_key": "taxAmtIpl2", "rate_key": "taxRtIpl2"},
    # 👉 Add more mappings for C1, C2, F, etc. as needed
}


# def build_invoice_payload(doc):
#     """
#     Convert ERPNext Sales Invoice doc into ZRA Smart Invoice payload.
#     """

#     payload = {
#         "tpin": "",
#         "bhfId": "000",
#         "orgInvcNo": 0,
#         "cisInvcNo": doc.name,
#         "custTpin": doc.tax_id or "2000000000",
#         "custNm": doc.customer_name,
#         "salesTyCd": "N",
#         "rcptTyCd": "S",
#         "pmtTyCd": "01",   # Cash (default)
#         "salesSttsCd": "02",
#         "cfmDt": now_datetime().strftime("%Y%m%d%H%M%S"),
#         "salesDt": nowdate().replace("-", ""),
#         "totItemCnt": len(doc.items),
#         # init totals
#         "totTaxblAmt": 0,
#         "totTaxAmt": 0,
#         "totAmt": 0,
#         # init category fields
#     }

#     # Init tax category fields
#     for key in ["A", "B", "C1", "C2", "C3", "D", "Rvat", "E", "F", "Ipl1", "Ipl2", "Tl", "Ecm", "Exeeg"]:
#         payload[f"taxblAmt{key}"] = 0
#         payload[f"taxRt{key}"] = 0
#         payload[f"taxAmt{key}"] = 0

#     item_list = []

#     # Process items
#     for idx, item in enumerate(doc.items, start=1):
#         cat_code = getattr(item, "taxation_type_code", None)
#         mapping = TAX_CATEGORY_MAP.get(cat_code)

#         vat_amount = 0
#         if mapping:
#             tax_rate = mapping["tax_rate"]
#             vat_amount = (item.base_net_amount * tax_rate) / 100

#             payload[mapping["taxbl_key"]] += item.base_net_amount
#             payload[mapping["tax_key"]] += vat_amount
#             payload[mapping["rate_key"]] = tax_rate

#         # Add to invoice totals
#         payload["totTaxblAmt"] += item.base_net_amount
#         payload["totTaxAmt"] += vat_amount

#         item_list.append({
#             "itemSeq": idx,
#             "itemCd": item.item_code,
#             "itemClsCd": getattr(item, "custom_class_code", "50102518"),
#             "itemNm": item.item_name,
#             "qty": item.qty,
#             "prc": item.rate,
#             "splyAmt": item.base_net_amount,
#             "dcRt": item.discount_percentage or 0,
#             "dcAmt": item.discount_amount or 0,
#             "vatCatCd": cat_code if cat_code in ["A", "B", "C1"] else None,
#             "iplCatCd": cat_code if "IPL" in (cat_code or "") else None,
#             "vatTaxblAmt": item.base_net_amount if cat_code in ["A", "B", "C1"] else 0,
#             "vatAmt": vat_amount if cat_code in ["A", "B", "C1"] else 0,
#             "iplTaxblAmt": item.base_net_amount if "IPL" in (cat_code or "") else 0,
#             "iplAmt": vat_amount if "IPL" in (cat_code or "") else 0,
#             "totAmt": item.base_net_amount + vat_amount - (item.discount_amount or 0),
#         })

#     # Grand totals
#     payload["totAmt"] = payload["totTaxblAmt"] + payload["totTaxAmt"] - (doc.discount_amount or 0)
#     payload["cashDcAmt"] = doc.discount_amount or 0
#     payload["itemList"] = item_list

#     return payload


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



def build_return_invoice_payload(doc, settings_name: str) -> dict:
    """
    Build payload for return (credit note) invoices to Crystal VSDC.
    Adapt fields as required by API spec.
    """
    return {
        "tpin": doc.company_tax_id,
        "bhfId": "000",
        "orgInvcNo": doc.return_against or "",
        "cisInvcNo": doc.name,
        "custTpin": doc.customer_tax_id,
        "salesTyCd": "R",  # return
        "salesDt": doc.posting_date.strftime("%Y%m%d"),
        "totAmt": doc.rounded_total or doc.grand_total,
        "remark": f"Credit Note for {doc.return_against}",
        "itemList": [
            {
                "itemSeq": i.idx,
                "itemCd": i.item_code,
                "itemNm": i.item_name,
                "qty": i.qty,
                "prc": i.rate,
                "totAmt": i.amount,
            }
            for i in doc.items
        ],
    }

