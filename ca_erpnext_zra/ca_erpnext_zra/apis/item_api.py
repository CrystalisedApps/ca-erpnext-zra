import frappe
from frappe import _
from ..utils.payload_utils import generate_vsdc_item_payload
from ..apis.api_processor import process_request
from ..utils.smart_api_utils import get_active_smart_settings


@frappe.whitelist()
def perform_item_registration(item_name: str, settings_name: str| None = None) -> dict | None:
    """Register an Item with Smart Zambia API (single settings setup)."""
    item = frappe.get_doc("Item", item_name)

    settings = _get_single_smart_settings()
    # frappe.throw(str(settings))
    if not settings:
        frappe.throw(_("No active Smart API Settings found"))

    if not is_item_eligible_for_registration(item):
        return None

    frappe.enqueue(
        process_request,
        queue="default",
        is_async=True,
        request_data=generate_vsdc_item_payload(item.name),
        route_key="SaveItem",
        handler_function=handle_registration_response,
        request_method="POST",
        doctype="Item",
        settings_name=settings["name"],
    )
    return {"queued": True, "item": item.name}


@frappe.whitelist()
def fetch_item_details(item_name: str) -> dict | None:
    """Fetch Item details from Smart Zambia API."""
    item = frappe.get_doc("Item", item_name)

    if not item.get("custom_smart_item_code"):
        frappe.throw(_("Smart Item Code not set for {0}").format(item.name))

    settings = _get_single_smart_settings()
    if not settings:
        frappe.throw(_("No active Smart API Settings found"))

    frappe.enqueue(
        process_request,
        queue="default",
        is_async=True,
        request_data={"itemCd": item.item_code},
        route_key="ItemFetchReq",
        handler_function=handle_fetch_response,
        request_method="GET",
        doctype="Item",
        settings_name=settings["name"],
    )
    return {"queued": True, "item": item.name}


@frappe.whitelist()
def update_item(item_name: str) -> dict | None:
    """Update Item details in Smart Zambia API."""
    item = frappe.get_doc("Item", item_name)

    if not is_item_eligible_for_registration(item):
        return None

    settings = _get_single_smart_settings()
    if not settings:
        frappe.throw(_("No active Smart API Settings found"))

    frappe.enqueue(
        process_request,
        queue="default",
        is_async=True,
        request_data=generate_vsdc_item_payload(item.name),
        route_key="ItemUpdateReq",
        handler_function=handle_update_response,
        request_method="POST",
        doctype="Item",
        settings_name=settings["name"],
    )
    return {"queued": True, "item": item.name}


@frappe.whitelist()
def submit_inventory(item_name: str) -> dict | None:
    """Submit inventory stock levels to Smart Zambia API."""
    item = frappe.get_doc("Item", item_name)

    settings = _get_single_smart_settings()
    if not settings:
        frappe.throw(_("No active Smart API Settings found"))

    request_payload = {
        "itemCd": item.item_code,
        "qty": item.get("actual_qty") or 0,
        "bhfId": settings.get("bhfId") or "000",
    }

    frappe.enqueue(
        process_request,
        queue="default",
        is_async=True,
        request_data=request_payload,
        route_key="InventorySubmitReq",
        handler_function=handle_inventory_response,
        request_method="POST",
        doctype="Item",
        settings_name=settings["name"],
    )
    return {"queued": True, "item": item.name}


# ----------------------------
# Helpers
# ----------------------------
def _get_single_smart_settings() -> dict | None:
    """Helper to return the single Smart settings dict or None."""
    settings = get_active_smart_settings()
    return settings[0] if settings else None


def is_item_eligible_for_registration(item) -> bool:
    """Check if item can be registered in Smart Zambia."""
    return not (item.get("custom_prevent_smart_registration") or item.disabled)


# ----------------------------
# Callback Handlers (placeholders)
# ----------------------------
def handle_registration_response(response, request_data):
    frappe.logger().info(f"[SMART] Registration Response: {response}")

    try:
        if response.get("IsSuccess") and response["Result"].get("resultCd") == "000":
            item_code = request_data.get("itemCd")  # from your payload
            if item_code:
                item = frappe.get_doc("Item", {"item_code": item_code})
                # mark item as registered
                item.db_set("custom_item_registered", 1)  
                frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"[SMART] Failed to process registration response: {e}")



def handle_fetch_response(response, request_data):
    frappe.logger().info(f"[SMART] Fetch Response: {response}")


def handle_update_response(response, request_data):
    frappe.logger().info(f"[SMART] Update Response: {response}")


def handle_inventory_response(response, request_data):
    frappe.logger().info(f"[SMART] Inventory Response: {response}")
