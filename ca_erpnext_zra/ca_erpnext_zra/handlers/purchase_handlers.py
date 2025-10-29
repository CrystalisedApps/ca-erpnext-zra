import frappe
from frappe.utils import flt, nowdate
from frappe.model.document import Document
from frappe.utils import get_datetime
from frappe.utils import flt
from frappe.utils import today

from ..doctype.doctype_names_mapping import REGISTERED_PURCHASES_DOCTYPE_NAME


def purchase_search_on_success(response: dict, **kwargs) -> None:
    sales_list = (
        response.get("Result", {})
        .get("data", {})
        .get("saleList", [])
    )
   
    for sale in sales_list:
        registered_purchase = create_purchase_from_smart_details(sale)
        frappe.enqueue(
            "ca_erpnext_zra.ca_erpnext_zra.apis.remote_response_status_handlers.fetch_purchase_items",
            registered_purchase=registered_purchase,
            queue="long",
        )

  








def create_purchase_from_smart_details(fetched_purchase: dict) -> str:
    """
    Create or update a 'Smart Registered Purchase' document in ERPNext
    from a fetched ZRA Smart Invoice saleList entry.
    Then create/update a linked Purchase Invoice and update stock.
    """

    purchase_id = f"{fetched_purchase['spplrTpin']}-{fetched_purchase['spplrBhfId']}-{fetched_purchase['spplrInvcNo']}"

    existing_doc = frappe.get_value(
        REGISTERED_PURCHASES_DOCTYPE_NAME, {"purchase_id": purchase_id}, "name"
    )

    if existing_doc:
        doc = frappe.get_doc(REGISTERED_PURCHASES_DOCTYPE_NAME, existing_doc)
    else:
        doc = frappe.new_doc(REGISTERED_PURCHASES_DOCTYPE_NAME)

    # Allow creation without permission checks or validation errors
    doc.flags.ignore_permissions = True
    doc.flags.ignore_validate_update_after_submit = True
    doc.purchase_id = purchase_id

    # ---------------- Supplier & Purchase Details ----------------
    doc.supplier_name = fetched_purchase.get("spplrNm")
    doc.supplier_tpin = fetched_purchase.get("spplrTpin")
    doc.supplier_branch_id = fetched_purchase.get("spplrBhfId")
    doc.supplier_invoice_no = fetched_purchase.get("spplrInvcNo")
    doc.receipt_type_code = fetched_purchase.get("rcptTyCd")
    doc.payment_type_code = fetched_purchase.get("pmtTyCd")
    doc.remark = fetched_purchase.get("remark")

    # ---------------- Transaction Info ----------------
    if fetched_purchase.get("cfmDt"):
        try:
            doc.confirmed_date = get_datetime(fetched_purchase["cfmDt"])
        except Exception:
            doc.confirmed_date = None

    if fetched_purchase.get("salesDt"):
        try:
            doc.sales_date = get_datetime(
                f"{fetched_purchase['salesDt'][:4]}-{fetched_purchase['salesDt'][4:6]}-{fetched_purchase['salesDt'][6:8]}"
            )
        except Exception:
            doc.sales_date = None

    if fetched_purchase.get("stockRlsDt"):
        try:
            doc.stock_release_date = get_datetime(fetched_purchase["stockRlsDt"])
        except Exception:
            doc.stock_release_date = None

    # ---------------- Totals ----------------
    doc.total_item_count = fetched_purchase.get("totItemCnt", 0)
    doc.total_taxable_amount = fetched_purchase.get("totTaxblAmt", 0.0)
    doc.total_tax_amount = fetched_purchase.get("totTaxAmt", 0.0)
    doc.total_amount = fetched_purchase.get("totAmt", 0.0)

    # ---------------- Item List ----------------
    doc.items = []
    for item in fetched_purchase.get("itemList", []):
        doc.append("items", {
            "item_seq": item.get("itemSeq"),
            "item_code": item.get("itemCd"),
            "item_name": item.get("itemNm"),
            "item_class_code": item.get("itemClsCd"),
            "package_unit_code": item.get("pkgUnitCd"),
            "quantity_unit_code": item.get("qtyUnitCd"),
            "quantity": flt(item.get("qty") or 1),
            "unit_price": flt(item.get("prc") or 0.0),
            "supply_amount": flt(item.get("splyAmt") or 0.0),
            "discount_rate": flt(item.get("dcRt") or 0.0),
            "discount_amount": flt(item.get("dcAmt") or 0.0),
            "taxable_amount": flt(item.get("taxblAmt") or 0.0),
            "vat_amount": flt(item.get("vatAmt") or 0.0),
            "total_amount": flt(item.get("totAmt") or 0.0),
            "vat_category_code": item.get("vatCatCd"),
        })

    # ---------------- Save & Submit Smart Registered Purchase ----------------
    doc.save(ignore_permissions=True)
    if doc.docstatus != 1:
        doc.submit()


    # ---------------- Create/Update Linked Purchase Invoice ----------------
    purchase_invoice_name = create_or_update_purchase_invoice_from_smart(doc)

    return purchase_invoice_name

def create_or_update_purchase_invoice_from_smart(doc):
    """
    Create or update a Purchase Invoice in ERPNext based on Smart (ZRA) data.
    Safe against missing fields, orphaned child rows, and validation edge cases.
    """

    # --- 1️⃣ Ensure Supplier Exists ---
    supplier_name = get_or_create_supplier_from_smart(doc)

    # --- 2️⃣ Find or Create Invoice ---
    existing_pi = frappe.db.get_value(
        "Purchase Invoice",
        {"custom_smart_purchase_id": doc.purchase_id or doc.smart_id},
        "name"
    )

    if existing_pi:
        #  Update existing invoice
        pi = frappe.get_doc("Purchase Invoice", existing_pi)
        pi.set("items", [])  # clear all previous rows safely
    else:
        # 🆕 Create new invoice
        pi = frappe.new_doc("Purchase Invoice")
        pi.custom_smart_purchase_id = doc.purchase_id or doc.smart_id
        pi.company = getattr(doc, "company", frappe.defaults.get_user_default("Company"))
        pi.supplier = supplier_name
        pi.bill_no = getattr(doc, "invoice_no", None) or getattr(doc, "spplrInvcNo", None)
        pi.bill_date = getattr(doc, "salesDt", today())
        pi.posting_date = today()
        pi.currency = "ZMW"  # or derive from Smart if available
        pi.buying_price_list = frappe.db.get_value("Buying Settings", None, "price_list") or "Standard Buying"

    # --- 3️⃣ Add Items ---
    for item in getattr(doc, "items", []):
        item_code = get_or_create_item_from_smart(item)

        qty = flt(getattr(item, "qty", 1))
        rate = flt(getattr(item, "prc", 0.0))
        amount = qty * rate
        uom = getattr(item, "qtyUnitCd", "Nos") or "Nos"
        conversion_factor = 1.0
        stock_qty = qty * conversion_factor

        # Get a valid default expense account
        default_expense_account = (
            frappe.db.get_value("Company", pi.company, "default_expense_account")
            or frappe.db.get_value("Company", pi.company, "stock_received_but_not_billed")
            or frappe.db.get_value("Account", {"company": pi.company, "root_type": "Expense"}, "name")
        )
        pi.append("items", {
            "item_code": item_code,
            "item_name": getattr(item, "itemNm", item_code),
            "description": getattr(item, "itemNm", item_code),
            "qty": qty,
            "stock_uom": uom,
            "uom": uom,
            "conversion_factor": conversion_factor,
            "stock_qty": stock_qty,
            "accepted_qty": qty,
            "rate": rate,
            "amount": amount,
            "base_rate": rate,
            "base_amount": amount,
            "received_qty": qty,
            "warehouse": frappe.db.get_value("Warehouse", {"company": pi.company}, "name") or "Main Warehouse",
           "expense_account": default_expense_account,   # ✅ Fix: ensure valid expense account

        })

    # --- 4️⃣ Force new child inserts (avoid old row references) ---
    for row in pi.items:
        row.name = None

    # --- 5️⃣ Safety Flags ---
    pi.flags.ignore_permissions = True
    pi.flags.ignore_validate_update_after_submit = True
    pi.flags.ignore_mandatory = True
    pi.flags.ignore_links = True
    pi.flags.ignore_validate = True

    # --- 6️⃣ Save Safely ---
    pi.save(ignore_permissions=True)
    frappe.db.commit()

    # --- 7️⃣ Optional: auto-submit if valid ---
    try:
        if not pi.docstatus:
            pi.submit()
            frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Smart Purchase: failed to submit {pi.name}")

    return pi.name



# ------------------- Utility Functions -------------------

def get_default_company() -> str:
    company = frappe.defaults.get_user_default("Company")
    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")
    return company


def get_default_warehouse() -> str:
    return frappe.db.get_value("Warehouse", {"is_group": 0}, "name")


def get_default_cost_center() -> str:
    return frappe.db.get_value("Cost Center", {"is_group": 0}, "name")

def get_or_create_item_from_smart(item_row) -> str:
    """
    Ensure an Item exists for the Smart Invoice purchase product (ZRA).
    Handles both dicts and Frappe Document objects like SmartRegisteredPurchaseItem.
    """

    def val(fieldname, default=None):
        """Safely extract field from dict or frappe._dict or Document."""
        if hasattr(item_row, fieldname):
            return getattr(item_row, fieldname, default)
        if isinstance(item_row, (dict, frappe._dict)):
            return item_row.get(fieldname, default)
        return default

    # Correct Smart field names
    item_code = val("item_code") 
    if not item_code:
        frappe.throw(f"Item code is missing in Smart item: {item_row.name}")

    existing_item = frappe.db.exists("Item", {"item_code": item_code})
    if existing_item:
        return existing_item

    # Units and VAT
    packaging_unit = val("packaging_unit_code", "EA")
    quantity_unit = val("quantity_unit_code", "Nos")
    vat_category = val("vat_category_code", "A")

    ensure_uom_exists(quantity_unit)
    ensure_uom_exists(packaging_unit)

    new_item = frappe.get_doc({
        "doctype": "Item",
        "item_code": item_code,
        "item_name": val("item_name"),
        "item_group": "Products",
        "is_stock_item": 1,
        "stock_uom": quantity_unit,
        "standard_rate": val("prc") or 0.0,
        "custom_item_classification": val("item_class_code"),
        "custom_smart_packaging_unit": packaging_unit,
        "custom_smart_quantity_unit": quantity_unit,
        "custom_smart_vat_category": vat_category,
    })

    new_item.insert(ignore_permissions=True)
    frappe.db.commit()
    return new_item.name


def ensure_uom_exists(uom_name: str):
    """Ensure a UOM record exists before linking."""
    if not uom_name:
        return
    if not frappe.db.exists("UOM", uom_name):
        frappe.get_doc({
            "doctype": "UOM",
            "uom_name": uom_name,
            "enabled": 1
        }).insert(ignore_permissions=True)


def get_or_create_supplier_from_smart(sale_data) -> str:
    """
    Ensure a Supplier exists for the Smart (ZRA) purchase record.
    Handles both dicts and Frappe Document types like CrystallisedZRASmartPurchases.
    """

    def val(fieldname, default=None):
        """Safely extract field from dict, frappe._dict, or Document."""
        if hasattr(sale_data, fieldname):
            return getattr(sale_data, fieldname, default)
        if isinstance(sale_data, (dict, frappe._dict)):
            return sale_data.get(fieldname, default)
        return default

    # ✅ Try all possible Smart field names (depending on sync type)
    supplier_name = (
        val("supplier_name")
        or val("seller_name")
        or val("supplierNm")
        or val("suppNm")
        or "Unknown Supplier"
    )

    supplier_tpin = (
        val("supplier_tpin")
        or val("seller_tpin")
        or val("suppTpin")
        or val("tpin")
        or ""
    )

    # ✅ Normalize values
    supplier_name = supplier_name.strip() if supplier_name else "Unknown Supplier"
    supplier_tpin = supplier_tpin.strip() if supplier_tpin else ""

    # 🧾 Check existing supplier by TPIN (preferred)
    existing_supplier = None
    if supplier_tpin:
        existing_supplier = frappe.db.exists("Supplier", {"tax_id": supplier_tpin})

    # 🔄 fallback check by supplier_name if no TPIN found
    if not existing_supplier and supplier_name:
        existing_supplier = frappe.db.exists("Supplier", {"supplier_name": supplier_name})

    if existing_supplier:
        return existing_supplier

    # 🏗️ Create new Supplier
    new_supplier = frappe.get_doc({
        "doctype": "Supplier",
        "supplier_name": supplier_name,
        "supplier_group": "All Supplier Groups",
        "tax_id": supplier_tpin,
        "supplier_type": "Company",
    })
    new_supplier.insert(ignore_permissions=True)
    frappe.db.commit()

    return new_supplier.name
