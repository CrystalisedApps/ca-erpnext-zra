import frappe
from frappe import _
from ..utils.payload_utils import generate_vsdc_item_payload
from ..apis.api_processor import process_request
from ..utils.smart_api_utils import get_active_smart_settings
from frappe.utils.background_jobs import enqueue


@frappe.whitelist()
def perform_item_registration(doc, method=None) -> dict | None:
    """Register an Item with Smart Zambia API (single settings setup)."""

    # frappe.throw(str(doc))
    import json

    # If doc is a string (from JS), convert it
    if isinstance(doc, str):
        doc = json.loads(doc)

    # Now, if it's a dict, get the actual Item record
    if isinstance(doc, dict):
        docname = doc.get("name")
    else:
        docname = getattr(doc, "name", None)

    if not docname:
        frappe.throw("No Item name provided for registration.")

    item = frappe.get_doc("Item", docname)

    # frappe.throw(str(item))
    settings = _get_single_smart_settings()
    if not settings:
        frappe.throw(_("No active Smart API Settings found"))

    if not is_item_eligible_for_registration(item):
        return None
    # frappe.throw(str(generate_vsdc_item_payload(item.name)))
  
    
    # Enqueue async job
    enqueue(
            "ca_erpnext_zra.ca_erpnext_zra.apis.item_api._process_item_registration",
        queue="long",  # or "default"
        job_name=f"Register Item {item.name} with Smart Zambia",
        timeout=300,
        item_name=item.name,
        settings_name=settings["name"],
    )

    return {
        "queued": True,
        "item": item.name,
        "message": "Item registration has been queued"
    }

def _process_item_registration(item_name: str, settings_name: str):
    try:
        item = frappe.get_doc("Item", item_name)
        payload = generate_vsdc_item_payload(item.name)

        response = process_request(
            request_data=payload,
            route_key="SaveItem",
            request_method="POST",
            handler_function=handle_registration_response,
            settings_name=settings_name,
        )

        # frappe.db.set_value("Item", item.name, "last_registration_response", str(response))
        frappe.db.commit()
        return response

    except Exception as e:
        frappe.log_error(
            title="Item Registration Failed",
            message=f"Item: {item_name}\nError: {frappe.get_traceback()}"
        )
        raise  # Let RQ mark the job as failed




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
        route_key="",
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
    # settings = frappe.get_all("Crystal ZRA Smart Invoice Settings", fields=["name","company_name","tpin", "server_url"])
    return settings[0] if settings else None


def is_item_eligible_for_registration(item) -> bool:
    """Check if item can be registered in Smart Zambia."""
    return not (item.get("custom_prevent_smart_registration") or item.disabled)


# ----------------------------
# Callback Handlers (placeholders)
# ----------------------------
def handle_registration_response(
    response,
    request_data=None,
    document_name=None,
    doctype=None,
    payload=None,
    settings_name=None,
):
    frappe.logger().info(f"[SMART] Registration Response: {response}")

    try:
        is_success = response.get("IsSuccess")
        result = response.get("Result") or {}
        result_cd = result.get("resultCd")

        if is_success and result_cd == "000":
            # Prefer payload (what we sent to ZRA) → fallback to request_data
            item_code = (payload or {}).get("itemCd") or (request_data or {}).get("itemCd")
            if not item_code:
                frappe.log_error("Missing itemCd in payload/request_data", "[SMART] Registration Handler")
                return

            # Fetch Item name
            item_name = frappe.db.get_value("Item", {"item_code": item_code}, "name")
            if not item_name:
                frappe.log_error(f"Item with code {item_code} not found", "[SMART] Registration Handler")
                return

            # Update Item as registered
            frappe.db.set_value("Item", item_name, "custom_item_registered", 1)

          

            frappe.db.commit()
            frappe.logger().info(f"[SMART] Item {item_code} marked as registered.")

        else:
            frappe.log_error(
                title="[SMART] Registration Failed",
                message=f"Response: {response}, Payload: {payload}"
            )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"[SMART] Failed to process registration response: {e}")


def handle_fetch_response(response, request_data):
    frappe.logger().info(f"[SMART] Fetch Response: {response}")


def handle_update_response(response, request_data):
    frappe.logger().info(f"[SMART] Update Response: {response}")


def handle_inventory_response(response, request_data):
    frappe.logger().info(f"[SMART] Inventory Response: {response}")
