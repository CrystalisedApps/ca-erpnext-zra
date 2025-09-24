from frappe.model.document import Document

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


from datetime import datetime
import frappe
from frappe.model.document import Document

# from .id_utils import get_vsdc_id


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
