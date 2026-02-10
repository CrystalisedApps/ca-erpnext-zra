import frappe
from frappe import _

# from ..utils.smart_api_utils import get_active_smart_settings
from frappe.utils.background_jobs import enqueue
from frappe.utils.password import get_decrypted_password
from frappe.utils.data import add_to_date
from datetime import datetime
from frappe.utils import flt
from ..utils.settings_utils import get_settings
from .api_processor import process_request
from ..utils.routes_utils import get_route_path

from ..apis.api_processor import process_request
from ..services.item_service import (
	fetch_matching_items_on_success,
	handle_registration_response,
	trigger_item_registration,
)
from ..utils.payload_utils import (
	build_stock_payload,
	generate_custom_item_code_smart,
	generate_vsdc_item_payload,
)
from ..utils.smart_api_utils import get_active_smart_settings
from ..utils.settings_utils import get_settings

@frappe.whitelist()
def perform_item_registration(doc, settings_name=None, branch=None,branch_code=None, method=None) -> dict | None:
	import json
	# frappe.throw(str(branch))
	# Handle both dict or string inputs (from frontend or hooks)
	if isinstance(doc, str):
		doc = json.loads(doc)
	if isinstance(doc, dict):
		docname = doc.get("name")
	else:
		docname = getattr(doc, "name", None)

	if not docname:
		frappe.throw("No Item name provided for registration.")

	item = frappe.get_doc("Item", docname)

	# Get the settings
	settings = get_settings(settings_name)
	if not settings:
		frappe.throw(_("No active Smart API Settings found."))

	settings_name = settings.get("name")

	# Validate eligibility and required fields before proceeding
	if not is_item_eligible_for_registration(item):
		frappe.msgprint(_("Item not eligible for registration."), alert=True)
		return None

	missing_fields = validate_required_fields(item)
	
	if missing_fields:
		frappe.msgprint(_("Missing required fields: {0}").format(", ".join(missing_fields)), alert=True)
		return None
	if hasattr(item, "has_value_changed"):
		is_tax_type_changed = item.has_value_changed("custom_vat_category_code")
	else:
		is_tax_type_changed = True  # Assume changed if dict

	if item.custom_vat_category_code and is_tax_type_changed:
		relevant_tax_templates = frappe.get_all(
            "Item Tax Template",
            filters={"custom_taxation_type": item.custom_vat_category_code},
            fields=["name"]
        )

		if relevant_tax_templates:
            # Clear existing taxes
			item.set("taxes", [])

            # Append correctly
			for template in relevant_tax_templates:
				# frappe.throw(str(template))
				item.append("taxes", {
                    "item_tax_template": template.name
                })

        # Save to persist
		# item.save(ignore_permissions=True)

	# Generate Smart Item code code if missing
	if not item.custom_smart_item_code:
		generate_and_set_smart_code(item)
	 
	# item.save(ignore_permissions=True)
	# frappe.db.commit()
	# Trigger direct registration (skip lookup)
	frappe.enqueue(
		"ca_erpnext_zra.ca_erpnext_zra.apis.item_api._process_item_registration_direct",
		queue="default",
		job_name=f"[SMART] Register item {item.name}",
		timeout=300,
		item_name=item.name,
		branch_code=branch_code,
		branch=branch,
		settings_name=settings_name,
	)

	return {
		"queued": True,
		"item": item.name,
		"message": _("Item registration has been queued for Smart Zambia."),
	}


@frappe.whitelist()
def _process_item_registration_direct(item_name: str, branch_code: str, branch: str, settings_name: str):
	"""Directly trigger saveItem/updateItem for an item (skipping selectItem)."""
	from ..services.item_service import trigger_item_registration
	
	trigger_item_registration(
		document_name=item_name,
		settings_name=settings_name,
		branch_code=branch_code,
		branch_name=branch
	)


@frappe.whitelist()
def fetch_item_details(item_code: str, branch: str, settings_name: str = None, document_name: str = None) -> dict:
	"""Fetch Item details from Smart Zambia API."""
	settings = get_settings(settings_name)
	if not settings:
		frappe.throw(_("No active Smart API Settings found"))

	tpin =settings.tpin
	branch_code = frappe.db.get_value("Branch", branch, "custom_branch_code") or "000"

	payload = {
		"tpin": tpin,
		"bhfId": branch_code or "000",
		"itemCd": item_code,
		"document_name": document_name,
	}

	frappe.enqueue(
		process_request,
		queue="default",
		is_async=True,
		request_data=payload,
		route_key="selectItem",
		handler_function=item_search_on_success,
		request_method="POST",
		doctype="Item",
		document_name=document_name,
		settings_name=settings["name"],
	)
	return {"queued": True, "item": item_code}


@frappe.whitelist()
def update_item(doc, method=None, settings_name=None, branch=None) -> dict | None:
	"""Update Item details in Smart Zambia API."""
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

	if not is_item_eligible_for_registration(item):
		return None

	# Get settings
	settings = get_settings(settings_name)
	if not settings:
		frappe.throw(_("No active Smart API Settings found."))

	# Get branch logic
	branch_code = "000"
	if branch:
		branch_code = frappe.db.get_value("Branch", branch, "custom_branch_code") or "000"

	frappe.enqueue(
		process_request,
		queue="default",
		is_async=True,
		request_data=generate_vsdc_item_payload(item.name, branch_code, settings["name"]),
		route_key="updateItem",
		handler_function=handle_update_response,
		request_method="POST",
		doctype="Item",
		document_name=item.name,
		settings_name=settings["name"],
	)
	return {"queued": True, "item": item.name}

@frappe.whitelist()
def submit_item_composition(document_name: str, branch: str = None):
    """
    Submits all item compositions in a given document to ZRA (saveItemComposition API).
    Called from client script.
    """
    if not document_name:
        frappe.throw("Document name is required.")

    doc = frappe.get_doc("BOM", document_name)  # Or your custom doctype

    # Use branch from BOM if available
    branch = doc.custom_smart_branch or branch

    # Resolve branch info
    if branch:
        bhf_id = frappe.db.get_value("Branch", branch, "custom_branch_code") or "000"
        company = frappe.db.get_value("Branch", branch, "custom_company")
    else:
        bhf_id = "000"
        company = doc.company

    if not company:
        frappe.throw("Company not found")

    settings = get_settings(company)
    if not settings:
        frappe.throw(f"No Smart Invoice settings found for company {company}")

    user = frappe.session.user.upper()

    # Default request date: 1 year back
    request_date = add_to_date(datetime.now(), years=-1).strftime("%Y%m%d%H%M%S")

    # Fetch last request date from DB if available
    try:
        _, last_req_date = get_route_path("saveItemComposition", "Crystal VSDC")
        last_req_dt = last_req_date.strftime("%Y%m%d%H%M%S") if last_req_date else request_date
    except Exception:
        last_req_dt = request_date

    # Loop over all items in the document
    for item in doc.items:
        item_code = item.item_code
        qty = flt(item.qty or 1)

        payload = {
            "tpin": settings.tpin,
            "bhfId": bhf_id,
            "itemCd": item_code,
            "cpstItemCd": item_code,
            "cpstQty": qty,
            "regrId": user,
            "regrNm": user,
            
        }

        # Enqueue each item submission
        frappe.enqueue(
            process_request,
            queue="default",
            request_data=payload,
            route_key="saveItemComposition",
            handler_function=None,
            request_method="POST",
            doctype="Item",
            document_name=item_code
        )

    return f"Enqueued submission of {len(doc.items)} items for ZRA Smart Invoice."

# @frappe.whitelist()
# def submit_inventory(item_name: str) -> dict | None:
#     """Submit inventory stock levels to Smart Zambia API."""
#     item = frappe.get_doc("Item", item_name)

#     settings = _get_single_smart_settings()
#     if not settings:
#         frappe.throw(_("No active Smart API Settings found"))

#     # Assign variables AFTER confirming settings exist
#     tpin = get_decrypted_password(
#         "Crystal ZRA Smart Invoice Settings",
#          settings["name"],
#         "tpin",
#         raise_exception=False
#     ) or ""

#     bhf_id = settings.get("bhfId") or "000"
#     user = frappe.session.user or "Admin"

#     request_payload = {
#         "itemCd": item.item_code,
#         "qty": item.get("actual_qty") or 0,
#         "bhfId": bhf_id,
#     }

#     # Prepare stock payload
#     stock_payload = build_stock_payload(
#         tpin=tpin,
#         bhf_id=bhf_id,
#         user=user,
#         stock_items=[request_payload],
#         route_key="SaveStockMaster",
#     )

#     frappe.enqueue(
#         process_request,
#         queue="default",
#         is_async=True,

#         request_data=stock_payload,
#         route_key="saveStockMaster",
#         handler_function=handle_inventory_response,
#         request_method="POST",
#         doctype="Item",
#         settings_name=settings["name"]
#     )

#     return {"queued": True, "item": item.name}


# ----------------------------
# Helpers
# ----------------------------
def _get_single_smart_settings() -> dict | None:
	"""Helper to return the single Smart settings dict or None."""
	settings = get_active_smart_settings()
	# settings = frappe.get_all("Crystal ZRA Smart Invoice Settings", fields=["name","company_name","tpin", "server_url"])
	return settings if settings else None


def is_item_eligible_for_registration(item) -> bool:
	"""Check if item can be registered in Smart Zambia."""
	return not (item.get("custom_prevent_smart_registration") or item.disabled)


def item_search_on_success(response: dict,branch: str, settings_name: str, **kwargs) -> None:
	"""
	Handles item search response from the ZRA Smart Invoice system.
	Creates or updates Item records in ERPNext based on ZRA item data.
	"""

	try:
		item_doc = None
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
					{"zra_item_code": zra_item_code, "branch": branch, "smart_setup": settings_name},
					"parent",
					order_by="creation desc",
				)

				# Country of origin (default to ZM if blank)
				country_code = (item_data.get("orgnNatCd") or "ZM").lower()
				country_link = get_link_value("Country", "code", country_code)

				# Set default UOM
				default_uom = item_data.get("qtyUnitCd") or "Nos"

				# Build item data
				# Build item data with truthy guards to prevent overwriting local data with blanks
				item_fields = {
					"item_name": item_name,
					"is_sales_item": True,
					"is_purchase_item": True,
					"valuation_rate": round(item_data.get("dftPrc", 0.0), 2),
					"last_purchase_rate": round(item_data.get("dftPrc", 0.0), 2),
					"stock_uom": default_uom,
					"uoms": [{"uom": default_uom, "conversion_factor": 1}],
					"custom_zra_item_code": zra_item_code,
					"custom_smart_item_code": zra_item_code,
					"custom_smart_quantity_unit": default_uom,
				}

				if item_data.get("itemClsCd"):
					item_fields["custom_smart_item_classification_code"] = item_data.get("itemClsCd")
				if item_data.get("itemTyCd"):
					item_fields["custom_smart_item_type"] = item_data.get("itemTyCd")
				if item_data.get("orgnNatCd"):
					country_code = item_data.get("orgnNatCd").lower()
					item_fields["custom_smart_country_of_origin_code"] = country_code
					country_link = get_link_value("Country", "code", country_code)
					if country_link:
						item_fields["custom_smart_country_of_origin_"] = country_link
				if item_data.get("pkgUnitCd"):
					item_fields["custom_smart_packaging_unit"] = item_data.get("pkgUnitCd")
				if item_data.get("vatCatCd"):
					item_fields["custom_vat_category_code"] = item_data.get("vatCatCd")
				if item_data.get("sftyQty"):
					item_fields["custom_smart_safety_quantity"] = round(item_data.get("sftyQty", 0.0), 2)
				# 1. Identify Target Item
				item_doc = None
				if existing_item:
					item_doc = frappe.get_doc("Item", existing_item)
				elif kwargs.get("document_name"):
					item_doc = frappe.get_doc("Item", kwargs.get("document_name"))
				
				# 2. Update existing or Create new
				if item_doc:
					# Create a copy of fields to avoid overwriting item_code
					update_data = item_fields.copy()
					if "item_code" in update_data:
						del update_data["item_code"]
					
					item_doc.update(update_data)
					# Manage Mapping
					existing_mapping_row = next(
						(r for r in item_doc.get("custom_smart_setup_mapping", [])
						 if r.smart_setup == settings_name and r.branch == branch),
						None
					)
					if not existing_mapping_row:
						item_doc.append("custom_smart_setup_mapping", {
							"smart_setup": settings_name,
							"zra_item_code": zra_item_code,
							"branch": branch
						})
					else:
						existing_mapping_row.zra_item_code = zra_item_code
					
					item_doc.flags.ignore_mandatory = True
					item_doc.save(ignore_permissions=True)
				else:
					# Fallback: Create new if truly unknown
					item_fields["item_group"] = frappe.db.get_value("Item Group", {"is_group": 1}, "name") or "All Item Groups"
					item_doc = frappe.get_doc({"doctype": "Item", **item_fields})
					item_doc.flags.ignore_mandatory = True
					item_doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_if_duplicate=True)
					
					# Add mapping record for branch
					frappe.get_doc({
						"doctype": "Smart Crystallised Mapping",
						"parent": item_doc.name,
						"parenttype": "Item",
						"parentfield": "custom_smart_setup_mapping",
						"zra_item_code": zra_item_code,
						"smart_setup": settings_name,
						"branch": branch
					}).insert(ignore_permissions=True)

			except Exception as e:
				frappe.log_error(title="ZRA Item Sync Error", message=f"Error: {e}")
				continue

		frappe.db.commit()

		# --- STEP 3: Trigger updateItem (Sync Details) ---
		# Capture a reference for the enqueue to ensure we hit the right item
		target_docname = kwargs.get("document_name") or (item_doc.name if 'item_doc' in locals() else None)
		
		if target_docname:
			frappe.logger().info(f"[SMART] selectItem Success for {target_docname}. Triggering updateItem")
			frappe.enqueue(
				update_item,
				queue="default",
				doc={"name": target_docname},
				settings_name=settings_name,
				branch=branch
			)
		else:
			frappe.logger().warning("[SMART] selectItem Success but no target_docname found. Chain stopped.")

	except Exception as e:
		frappe.log_error(
			title="ZRA Item Sync Fatal Error",
			message=f"Unexpected structure or processing failure: {str(e)}",
		)


def get_link_value(doctype, fieldname, value):
	return frappe.db.get_value(doctype, {fieldname: value}, "name")


def handle_update_response(response, document_name=None, payload=None, **kwargs):
	frappe.logger().info(f"[SMART] Update Response: {response}")

	if not document_name and payload:
		document_name = payload.get("itemNm")
	
	if not document_name:
		return

	if response.get("IsSuccess") is True:
		frappe.logger().info(f"[SMART] updateItem Success for {document_name}. Triggering saveStockItems (on_update)")

	# --- STEP 4: Trigger saveStockItems (Stock Link) ---
	latest_sle = frappe.db.get_value(
		"Stock Ledger Entry",
		{"item_code": document_name},
		"name",
		order_by="creation desc"
	)

	if latest_sle:
		from ..overrides.server.stock_ledger_entry import on_update
		sle_doc = frappe.get_doc("Stock Ledger Entry", latest_sle)
		frappe.enqueue(
			on_update,
			queue="default",
			doc=sle_doc
		)


def handle_inventory_response(response, **kwargs):
	frappe.logger().info(f"[SMART] Inventory Response: {response}")


def validate_required_fields(item) -> list:
	"""Validate required fields for item registration"""
	required_fields = [
		"custom_smart_item_classification_code",
		"custom_smart_item_type",
		"custom_smart_country_of_origin_",
		"custom_smart_packaging_unit",
		"custom_smart_quantity_unit",
		"custom_vat_category_code",
	]
	return [field for field in required_fields if not item.get(field)]


def generate_and_set_smart_code(item) -> None:
	"""Generate and set Smart code for item"""
	item.custom_smart_item_code = generate_custom_item_code_smart(item)
	frappe.db.set_value("Item", item.name, "custom_smart_item_code", item.custom_smart_item_code)
	frappe.db.commit()
