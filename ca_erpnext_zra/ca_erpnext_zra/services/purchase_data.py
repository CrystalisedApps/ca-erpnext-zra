import frappe
from datetime import datetime


def map_zra_purchase_to_erpnext(zra_purchase, company_name):
    pi = frappe.new_doc("Purchase Invoice")
    pi.company = company_name
    pi.supplier = zra_purchase["spplrNm"]
    pi.bill_no = zra_purchase["spplrInvcNo"]
    pi.posting_date = frappe.utils.getdate(zra_purchase["salesDt"])
    pi.update_stock = 1

    for item in zra_purchase["itemList"]:
        pi.append("items", {
            "item_code": item["itemCd"],
            "item_name": item["itemNm"],
            "qty": item["qty"] or 1,
            "rate": item["prc"],
            "uom": item.get("qtyUnitCd") or "Nos",
            "warehouse": "Main Warehouse - ABC"
        })

    pi.insert(ignore_permissions=True)
    pi.submit()

    frappe.db.set_value("Purchase Invoice", pi.name, "custom_stock_updated", 1)

    # Now resubmit back to ZRA
    submit_smart_purchase_invoice(pi)
