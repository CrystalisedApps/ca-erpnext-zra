
import frappe
from frappe.utils import nowdate
from frappe.utils.password import get_decrypted_password
from ..utils.settings_utils import get_settings
from ..utils.payload_utils import build_stock_payload
from .api_processor import process_request
from ..utils.payload_utils import build_sales_payload
from ..utils.payload_utils import build_stock_item_payload


@frappe.whitelist()
def send_stock_item_to_zra(doc, method):
    payload = build_stock_item_payload(doc)
    process_request(
        request_data=payload,
        route_key="saveStockItems",
        request_method="POST",
        doctype=doc.doctype,
        document_name=doc.name,
    )


@frappe.whitelist()
def send_sales_to_zra(doc, method):
    try:
        company_name = doc.company
        
        settings = get_settings()
        tpin = get_decrypted_password(
            "Crystal ZRA Smart Invoice Settings",
            settings.name,      
            "tpin",               # fieldname
            raise_exception=False
        ) or ""
        if not settings:
            frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings for {company_name}")
            return

        payload = build_sales_payload(doc.name, company_tpin=tpin, user=frappe.session.user)

        process_request(
            request_data=payload,
            route_key="saveStockItems", 
            request_method="POST",
            doctype="Sales Invoice",
            document_name=doc.name,
        )

        frappe.logger().info(f"✅ Successfully queued sales submission for {doc.name}")

       # --- Enqueue async stock sync job ---
        frappe.enqueue(
            "ca_erpnext_zra.ca_erpnext_zra.apis.stock_api.sync_stock_to_zra",
            queue="long",
            company_name=company_name,
            tpin=tpin,
           
            now=False  # async
        )

        frappe.logger().info(f"🧭 Enqueued stock sync job for {company_name}")

    except Exception:
        frappe.log_error(
            title="ZRA Sales Submission Error",
            message=f"Error processing {doc.name} for {company_name}:\n{frappe.get_traceback()}",
        )



def sync_stock_to_zra(company_name: str, tpin: str):
    """Sync stock quantities to ZRA Smart Invoice for the given company."""
    try:
        # Fetch stock data from ERPNext
        stock_data = frappe.db.sql("""
            SELECT item_code, SUM(actual_qty) AS qty
            FROM `tabBin`
            WHERE company = %s
            GROUP BY item_code
        """, (company_name,), as_dict=True)

        if not stock_data:
            frappe.logger().info(f"No stock data found for {company_name}, skipping sync.")
            return

        # Get branch and user info from settings
        settings = get_settings(company_name)
        bhf_id = settings.get("branch_id") or "000"
        user = frappe.session.user or "Admin"

        # Build payload dynamically
        stock_payload = build_stock_payload(
            tpin=tpin,
            bhf_id=bhf_id,
            user=user,
            stock_items=stock_data,
        )

        # Submit to Smart Invoice API
        process_request(
            request_data=stock_payload,
            route_key="SaveStockMaster",
            request_method="POST",
            doctype="Stock Entry",
            document_name=f"Auto Sync - {company_name}",
        )

        frappe.logger().info(f"📦 Successfully synced stock for {company_name}")

    
    except Exception:
        frappe.log_error(
            title="ZRA Stock Sync Error",
            message=f"Error syncing stock for {company_name}:\n{frappe.get_traceback()}",
        )



@frappe.whitelist()
def sync_stock_from_sle(doc, method=None):
    """Triggered from Stock Ledger Entry — sync stock movement to ZRA Smart Invoice."""
    try:
        company = doc.company
        settings = get_settings(company)
        if not settings:
            frappe.log_error("ZRA Settings Missing", f"No Smart Invoice settings for {company}")
            return

        tpin = get_decrypted_password(
            "Crystal ZRA Smart Invoice Settings",
            settings.name,
            "tpin",
            raise_exception=False
        ) or ""

        bhf_id = settings.get("bhfid") or "000"
        user = frappe.session.user or "Admin"

        # Choose the correct route
        if doc.actual_qty > 0:
            route_key = "saveStockItems"     # incoming stock → SaveStockItems
        elif doc.actual_qty < 0:
            route_key = "SaveStockMaster"    # outgoing or adjustment → SaveStockMaster
        else:
            frappe.logger().info(f"⚠️ Skipping zero-qty SLE {doc.name}")
            return

        # Build full item data (esp. for SaveStockItems)
        stock_item = {
            "itemCd": doc.item_code,
            "qty": abs(doc.actual_qty),
            "rsdQty": abs(doc.actual_qty),
            "prc": frappe.db.get_value("Item", doc.item_code, "valuation_rate") or 100,
            "itemNm": frappe.db.get_value("Item", doc.item_code, "item_name"),
        }

        # Prepare payload
        stock_payload = build_stock_payload(
            tpin=tpin,
            bhf_id=bhf_id,
            user=user,
            stock_items=[stock_item],
            route_key=route_key,
        )

        # Enqueue async call
        frappe.enqueue(
            "ca_erpnext_zra.ca_erpnext_zra.apis.api_processor.process_request",
            queue="long",
            request_data=stock_payload,
            route_key=route_key,
            request_method="POST",
            doctype="Stock Ledger Entry",
            document_name=doc.name,
            now=False,
        )

        frappe.logger().info(f"📦 Enqueued ZRA sync for SLE {doc.name} ({route_key})")

    except Exception:
        frappe.log_error(
            title="ZRA SLE Sync Error",
            message=f"Error syncing SLE {doc.name}:\n{frappe.get_traceback()}",
        )
