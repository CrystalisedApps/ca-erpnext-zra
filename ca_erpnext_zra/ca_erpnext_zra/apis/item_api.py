import frappe
from frappe import _

# from ..utils.smart_api_utils import get_active_smart_settings
from frappe.utils.background_jobs import enqueue
from frappe.utils.password import get_decrypted_password

from ..apis.api_processor import process_request
from ..services.item_service import fetch_matching_items_on_success, handle_registration_response
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
	# Step 1: Enqueue async GET to check if item already exists remotely
	frappe.enqueue(
		"ca_erpnext_zra.ca_erpnext_zra.apis.item_api._process_item_lookup",
		queue="default",
		job_name=f"[SMART] Lookup existing item {item.name}",
		timeout=300,
		item_name=item.name,
		branch_code=branch_code,
		branch=branch,
		settings_name=settings_name,
	)

	return {
		"queued": True,
		"item": item.name,
		"message": _("Item lookup has been queued for Smart Zambia registration."),
	}


@frappe.whitelist()
def _process_item_lookup(item_name: str,branch_code: str, branch: str, settings_name: str):
	"""Search for existing Smart Zambia item before registration (selectItem)."""
	from ..apis.api_processor import process_request

	# Fetch Item and settings
	item = frappe.get_doc("Item", item_name)
	settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
	tpin = settings.get("tpin")
	if branch_code:
		bhf_id = branch_code
	elif branch:
        # Fetch the branch code from the Branch DocType
		bhf_id = frappe.db.get_value("Branch", branch, "custom_branch_code") or "000"
	else:
		bhf_id = "000"
	item_cd = item.get("custom_smart_item_code")
	if not (tpin and item_cd):
		frappe.log_error(
			title="[SMART] Missing Required Data for selectItem",
			message=f"TPIN: {tpin}, Item Code: {item_cd}, Item: {item.name}",
		)
		return

	# Build the expected Smart Zambia API request payload
	request_data = {"tpin": tpin, "bhfId": bhf_id, "itemCd": item_cd}

	frappe.logger().info(f"[SMART]  Looking up existing Smart item: {request_data}")

	# Enqueue Smart API call
	frappe.enqueue(
		process_request,
		queue="default",
		is_async=True,
		request_data=request_data,
		route_key="selectItem",  # Smart API endpoint
		handler_function=fetch_matching_items_on_success,
		request_method="POST",
		doctype="Item",
		document_name=item.name,
		settings_name=settings_name,
		bhfid=bhf_id,
		branch=branch,
		error_callback=fetch_matching_items_on_success,
		
		
	)


@frappe.whitelist()
def fetch_item_details(item_code: str, branch: str,settings_name: str = None) -> None:
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
		settings_name=settings["name"],
	)
	return {"queued": True, "item": item_code}


@frappe.whitelist()
def update_item(doc, method=None) -> dict | None:
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

	settings = _get_single_smart_settings()
	if not settings:
		frappe.throw(_("No active Smart API Settings found"))

	frappe.enqueue(
		process_request,
		queue="default",
		is_async=True,
		request_data=generate_vsdc_item_payload(item.name),
		route_key="updateItem",
		handler_function=handle_update_response,
		request_method="POST",
		doctype="Item",
		settings_name=settings["name"],
	)
	return {"queued": True, "item": item.name}


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
						frappe.db.get_value("Item Group", {"is_group": 1}, "name") or "All Item Groups"
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
						{"zra_item_code": zra_item_code, "branch": branch},
					)
				else:
					frappe.get_doc(
						{
							"doctype": "Smart Crystallised Mapping",
							"parent": item_doc.name,
							"parenttype": "Item",
							"parentfield": "custom_smart_setup_mapping",
							"zra_item_code": zra_item_code,
							"smart_setup": settings_name,
							"branch": branch
						}
					).insert(ignore_permissions=True)

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
