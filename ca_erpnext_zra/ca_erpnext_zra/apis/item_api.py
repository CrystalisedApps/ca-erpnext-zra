import frappe
from frappe import _
from ..utils.payload_utils import generate_vsdc_item_payload
from ..apis.api_processor import process_request
from ..utils.smart_api_utils import get_active_smart_settings
from frappe.utils.background_jobs import enqueue
from frappe.utils.password import get_decrypted_password



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
def fetch_item_details(item_code: str, settings_name: str = None) -> None:
    """Fetch Item details from Smart Zambia API."""
    settings = _get_single_smart_settings()
    if not settings:
         frappe.throw(_("No active Smart API Settings found"))

    tpin = get_decrypted_password(
            "Crystal ZRA Smart Invoice Settings",
            settings["name"],
            "tpin",
            raise_exception=False
        ) or ""
    payload = {
    "tpin": tpin,
    "bhfId":  "000",
    "itemCd": item_code,
}

    frappe.enqueue(
        process_request,
        queue="default",
        is_async=True,
        request_data=payload,
        route_key="selectItem",
        handler_function= item_search_on_success,
        request_method="POST",
        doctype="Item",
        settings_name=settings["name"],
    )
    return {"queued": True, "item": item_code}


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


def item_search_on_success(response: dict, settings_name: str, **kwargs) -> None:
    """
    Handles item search response from the ZRA Smart Invoice system.
    Creates or updates Item records in ERPNext based on ZRA item data.
    """

    try:
        # Extract nested data safely
        result = response.get("Result", {})
        data = result.get("data", {})
        item_list = data.get("itemList", [])

        if not item_list:
            frappe.log_error("ZRA Item Sync", "No items found in response.")
            return

        for item_data in item_list:
            try:
                # Basic identification
                zra_item_code = item_data.get("itemCd")
                item_name = item_data.get("itemNm", "Unknown Item")

                # Check for existing mapping
                existing_item = frappe.db.get_value(
                    "Smart Crystallised Mapping",
                    {"zra_item_code": zra_item_code, "smart_setup": settings_name},
                    "parent",
                    order_by="creation desc",
                )

                # Country of origin (default to ZM if blank)
                country_code = (item_data.get("orgnNatCd") or "ZM").lower()
                country_link = get_link_value("Country", "code", country_code)

                # Set default UOM
                default_uom = item_data.get("qtyUnitCd") or "Nos"

                # Build item data
                item_fields = {
                    "item_name": item_name,
                    "item_code": zra_item_code,
                    "description": item_data.get("itemStdNm", item_name),
                    "is_sales_item": True,
                    "is_purchase_item": True,
                    "valuation_rate": round(item_data.get("dftPrc", 0.0), 2),
                    "last_purchase_rate": round(item_data.get("dftPrc", 0.0), 2),
                    "stock_uom": default_uom,
                    "uoms": [{"uom": default_uom, "conversion_factor": 1}],
                    # Custom ZRA fields
                    "custom_zra_item_code": zra_item_code,
                    "custom_smart_item_classification": item_data.get("itemClsCd", ""),
                    "custom_smart_item_type": item_data.get("itemTyCd", ""),
                    "custom_smart_country_of_origin_code": country_code,
                    "custom_smart_country_of_origin": country_link or "",
                    "custom_smart_packaging_unit": item_data.get("pkgUnitCd", ""),
                    "custom_smart_quantity_unit": default_uom,
                    "custom_smart_vat_category": item_data.get("vatCatCd", ""),
                    "custom_smart_safety_quantity": round(item_data.get("sftyQty", 0.0), 2),
                }

                if existing_item:
                    item_doc = frappe.get_doc("Item", existing_item)
                    item_doc.update(item_fields)

                    # Remove duplicate UOMs
                    if hasattr(item_doc, "uoms") and item_doc.uoms:
                        seen_uoms = set()
                        unique_uoms = []
                        for row in item_doc.uoms:
                            if row.uom not in seen_uoms:
                                unique_uoms.append(row)
                                seen_uoms.add(row.uom)
                        item_doc.uoms = unique_uoms

                    # Remove duplicate or extra Item Defaults (important: do this BEFORE save)
                    if hasattr(item_doc, "item_defaults") and item_doc.item_defaults:
                        seen_companies = set()
                        unique_defaults = []
                        for row in item_doc.item_defaults:
                            if row.company not in seen_companies:
                                unique_defaults.append(row)
                                seen_companies.add(row.company)
                        item_doc.item_defaults = unique_defaults

                    # Save only once
                    item_doc.flags.ignore_mandatory = True
                    item_doc.save(ignore_permissions=True)

                     # Remove duplicate or extra Item Defaults
                    if hasattr(item_doc, "item_defaults") and item_doc.item_defaults:
                        seen_companies = set()
                        unique_defaults = []
                        for row in item_doc.item_defaults:
                            if row.company not in seen_companies:
                                unique_defaults.append(row)
                                seen_companies.add(row.company)
                        item_doc.item_defaults = unique_defaults

                    item_doc.flags.ignore_mandatory = True
                    item_doc.save(ignore_permissions=True)
                else:
                    item_fields["item_group"] = (
                        frappe.db.get_value("Item Group", {"is_group": 1}, "name")
                        or "All Item Groups"
                    )
                    item_doc = frappe.get_doc({"doctype": "Item", **item_fields})
                    item_doc.flags.ignore_mandatory = True
                    item_doc.insert(
                        ignore_permissions=True,
                        ignore_mandatory=True,
                        ignore_if_duplicate=True,
                    )

                # Maintain mapping (ZRA → ERPNext)
                existing_mapping = frappe.db.exists(
                    "Smart Crystallised Mapping",
                    {
                        "parent": item_doc.name,
                        "parenttype": "Item",
                        "parentfield": "custom_smart_setup_mapping",
                        "smart_setup": settings_name,
                    },
                )

                if existing_mapping:
                    frappe.db.set_value(
                        "Smart Crystallised Mapping",
                        existing_mapping,
                        {"zra_item_code": zra_item_code},
                    )
                else:
                    frappe.get_doc({
                        "doctype": "Smart Crystallised Mapping",
                        "parent": item_doc.name,
                        "parenttype": "Item",
                        "parentfield": "custom_smart_setup_mapping",
                        "zra_item_code": zra_item_code,
                        "smart_setup": settings_name,
                    }).insert(ignore_permissions=True)

            except Exception as e:
                frappe.log_error(
                    title="ZRA Item Sync Error",
                    message=f"Error processing item {item_data.get('itemCd')}: {str(e)}",
                )
                continue

        frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            title="ZRA Item Sync Fatal Error",
            message=f"Unexpected structure or processing failure: {str(e)}",
        )



def get_link_value(doctype, fieldname, value):
    return frappe.db.get_value(doctype, {fieldname: value}, "name")


def handle_update_response(response, request_data):
    frappe.logger().info(f"[SMART] Update Response: {response}")


def handle_inventory_response(response, request_data):
    frappe.logger().info(f"[SMART] Inventory Response: {response}")
