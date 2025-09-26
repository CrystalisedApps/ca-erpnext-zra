from datetime import datetime
import frappe
from frappe.model.document import Document


# from .id_utils import get_vsdc_id









def generate_vsdc_item_payload(item_name: str) -> dict:
    """
    Generate Crystal VSDC Item payload from ERPNext Item doc.
    Assumes Item has custom fields linked to 'Crystallised Smart' doctypes.
    """

    item = frappe.get_doc("Item", item_name)

    def get_code(fieldname: str) -> str | None:
        """Fetch the .code from linked Crystallised Smart doctype"""
        if not item.get(fieldname):
            return None
        return frappe.db.get_value(item.meta.get_field(fieldname).options, item.get(fieldname), "code")

    payload = {
        "tpin": frappe.db.get_single_value(" Settings", "tpin") or "",
        "bhfId": "000",  # branch ID - may need dynamic if multi-branch

        "itemCd": item.item_code,
        "itemClsCd": get_code("custom_smart_item_classification_code"),   # Link → Crystallised Smart Item Type
        "itemTyCd": get_code("custom_smart_item_type"),              # Link → Crystallised Smart Item Type
        "itemNm": item.item_name,
        "itemStdNm": item.item_name,  # assuming same as itemNm
        "orgnNatCd": get_code("custom_smart_country_of_origin"),          # Link → Crystallised Smart Countries
        "pkgUnitCd": get_code("custom_smart_packaging_unit_code"),        # Link → Crystallised Smart Packing Unit
        "qtyUnitCd": get_code("custom_smart_quantity_unit_code"),         # Link → Crystallised Smart Quantity Unit
        "vatCatCd": get_code("vat_category_code"),           # Link → Crystallised Smart VAT Type
        "iplCatCd": get_code("ipl_category_code"),           # Link → Crystallised Smart IPL Registration Status
        "tlCatCd": get_code("trade_levy_category"),          # Link → Crystallised Smart Tourism Levy
        "exciseTxCatCd": get_code("excise_tax_category"),    # Link → Crystallised Smart Excise Duties
        "btchNo": item.get("batch_number") or None,
        "bcd": item.get("barcode") or None,
        "dftPrc": float(item.recommended_retail_price) if item.recommended_retail_price else 0,
        "manufacturerTpin": item.get("manufacturer_tpin") or None,
        "manufacturerItemCd": item.get("manufacturer_item_code") or None,
        "rrp": float(item.get("recommended_retail_price") or 0),
        "svcChargeYn": "Y" if item.get("is_service_charge_applicable") else "N",
        "rentalYn": get_code("rental_income_status"),        # Link → Crystallised Smart Rental Income Status
        "addInfo": item.get("additional_info") or None,
        "sftyQty": float(item.get("safety_stock") or 0),
        "isrcAplcbYn": get_code("insurance_applicable"),     # Link → Crystallised Smart Insurance Premium Levy
        "useYn": "Y" if item.disabled == 0 else "N",
        "regrNm": frappe.session.user,
        "regrId": frappe.session.user,
        "modrNm": frappe.session.user,
        "modrId": frappe.session.user,
    }

    return payload


def build_invoice_payload(invoice: Document, settings_name: str) -> dict:
    """
    Build a Crystal VSDC-compatible Sales Invoice payload from ERPNext Sales Invoice.

    Args:
        invoice (Document): ERPNext Sales Invoice or POS Invoice.
        settings_name (str): Crystal VSDC settings doc.

    Returns:
        dict: Payload for /SalesInvoiceSaveReq endpoint.
    """

    # Format datetime
    date_str = f"{invoice.posting_date} {invoice.posting_time or '00:00:00'}"
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in date_str else "%Y-%m-%d %H:%M:%S"
    sales_dt = datetime.strptime(date_str, fmt).strftime("%Y-%m-%dT%H:%M:%SZ")

    reference_number = get_invoice_reference_number(invoice)

    # Company + customer info
    company = frappe.get_doc("Company", invoice.company)
    customer = frappe.get_doc("Customer", invoice.customer)

    payload = {
        "tpin": company.tax_id,  # ZRA Taxpayer PIN
        "bhfId": company.custom_branch_id,  # branch id mapped in Crystal
        "cisInvcNo": reference_number,
        "salesDt": sales_dt,
        "custTpin": customer.tax_id,
        "custNm": customer.customer_name,
        "currencyTyCd": invoice.currency,
        "totItemCnt": len(invoice.items),
        "totAmt": invoice.grand_total,
        "totTaxAmt": invoice.total_taxes_and_charges,
        "totTaxblAmt": invoice.net_total,
        "remark": invoice.remarks or "",
        "itemList": [],
    }

    # Build item list
    for idx, item in enumerate(invoice.items, start=1):
        payload["itemList"].append({
            "itemSeq": idx,
            "itemCd": item.item_code,
            "itemNm": item.item_name,
            "itemClsCd": item.custom_classification_code or "",
            "qty": item.qty,
            "qtyUnitCd": item.uom,
            "prc": item.rate,
            "splyAmt": item.amount,
            "tlAmt": item.net_amount,
            "vatAmt": item.tax_amount or 0,
            "vatTaxblAmt": item.net_amount,
            "pkg": item.get("package_qty") or 1,
            "pkgUnitCd": item.get("package_unit") or "EA",  # default to Each
            # placeholders for Crystal fields
            "dcAmt": 0,
            "dcRt": 0,
            "tlTaxblAmt": item.net_amount,
            "totAmt": item.amount,
            "bcd": item.barcode or "",
        })

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




