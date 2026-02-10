import frappe

from ..utils.payload_utils import generate_vsdc_item_payload
from ..utils.response_utils import parse_response_data
from ..utils.settings_utils import get_settings
def handle_registration_response(
    response,
    request_data=None,
    document_name=None,
    doctype=None,
    payload=None,
    settings_name=None,
    branch=None,
    bhfid=None
):
    """
    Handles ZRA Smart Invoice item registration (POST/PATCH) response.
    Links the registered itemCd to local Item via Smart Crystallised Mapping.
    """
    frappe.logger().info(f"[SMART] Registration Response: {frappe.as_json(response)}")

    try:
        is_success = response.get("IsSuccess")
        result = response.get("Result") or {}
        result_cd = result.get("resultCd")
        result_data = result.get("data") or {}

        if is_success and result_cd == "000":
            # Determine item code
            item_code = (
                (payload or {}).get("itemCd")
                or (request_data or {}).get("itemCd")
                or result_data.get("itemCd")
            )

            if not item_code:
                frappe.log_error(
                    "[SMART] Missing itemCd in payload/request_data/response", "Registration Handler"
                )
                return

            # Find ERPNext Item
            item_name = frappe.db.get_value(
                "Item", {"custom_smart_item_code": item_code}, "name"
            )
            if not item_name:
                frappe.log_error(
                    f"[SMART] Item with code {item_code} not found", "Registration Handler"
                )
				
                return

            zra_item_code = result_data.get("itemCd") or result.get("ItemCd") or item_code

            # Load the item doc
            item_doc = frappe.get_doc("Item", item_name)
            found = False

            # Update existing mapping in-memory
            for row in item_doc.get("custom_smart_setup_mapping", []):
                if row.smart_setup == settings_name:
                    row.zra_item_code = zra_item_code
                    row.branch = branch
                    found = True
                    break

            # Append new mapping if not found
            if not found:
                item_doc.append(
                    "custom_smart_setup_mapping",
                    {
                        "smart_setup": settings_name,
                        "zra_item_code": zra_item_code,
                        "branch": branch,
                    },
                )

            #  Set registered checkbox before saving
            item_doc.custom_item_registered = 1
            item_doc.save(ignore_permissions=True)
            frappe.db.commit()

            frappe.logger().info(
                f"[SMART] Registered: {item_code} → ZRA Code: {zra_item_code} | Branch: {branch}"
            )

            # --- STEP 2: Trigger selectItem (Fetch Details) ---
            from ..apis.item_api import fetch_item_details
            frappe.logger().info(f"[SMART] saveItem Success for {item_name}. Triggering selectItem (fetch_item_details)")
            frappe.enqueue(
                fetch_item_details,
                queue="default",
                item_code=zra_item_code,
                branch=branch,
                settings_name=settings_name,
                document_name=item_name
            )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), f"[SMART] Failed to process registration response: {e}"
        )


def fetch_matching_items_on_success(response: dict, document_name: str, settings_name: str, bhfid,branch, **kwargs) -> None:
	"""
	Handles Smart Zambia (ZRA) item search response.
	Checks for matching items, archives duplicates if found,
	and registers or creates the ERPNext Item accordingly.
	"""
	from ..apis.api_processor import process_request
	
	frappe.logger().info(f"[SMART] Callback received BHFID: {bhfid}")
	items = parse_response_data(response, list)
	item_doc = frappe.get_doc("Item", document_name)

	# Check for existing mapping
	existing_mapping = next(
		(
			row.zra_item_code
			for row in item_doc.get("custom_smart_setup_mapping", [])
				if row.smart_setup == settings_name
		),
		None,
	)

	# --- CASE 1: Remote items exist ---
	if items:
		if not existing_mapping:
			frappe.get_doc(
				{
					"doctype": "Smart Crystallised Mapping",
					"parent": item_doc.name,
					"parenttype": "Item",
					"parentfield": "custom_smart_setup_mapping",
					"zra_item_code": items[0].get("itemCd"),
					"smart_setup": settings_name,
				}
			).insert(ignore_permissions=True)
			existing_mapping = items[0].get("itemCd")

		# Archive duplicates
		for item in items:
			if existing_mapping != item.get("itemCd"):
				frappe.enqueue(
					process_request,
					queue="default",
					doctype="Item",
					request_data={
						"document_name": item_doc.name,
						"name": f"{item_doc.name} - Archived",
						"itemCd": item.get("itemCd"),
						"useYn": "N",
					},
					route_key="updateItem",
					handler_function=item_archive_on_success,
					request_method="POST",
					settings_name=settings_name,
				)

	# --- CASE 2: No remote item found, trigger new item creation ---
	elif response.get("IsSuccess") is False:
		error_message = response.get("ErrorMessage", "").lower()
		if "no search result" in error_message or "error code: 001" in error_message:
			frappe.logger().info(
				f"[SMART] No existing ZRA item found for {item_doc.name}, creating new item."
			)
			existing_mapping = None 
	
	
def trigger_item_registration(document_name: str, settings_name: str, branch_code: str = None, branch_name: str = None):
	"""
	Triggers the actual saveItem/updateItem API calls for an item.
	This can be called directly to skip the preliminary selectItem check.
	"""
	from ..apis.api_processor import process_request
	
	item_doc = frappe.get_doc("Item", document_name)
	
	# Check for existing mapping
	existing_mapping = next(
		(
			row.zra_item_code
			for row in item_doc.get("custom_smart_setup_mapping", [])
				if row.smart_setup == settings_name
		),
		None,
	)

	branch_mappings = get_all_branch_mappings(settings_name)

	# If specific branch info provided, filter for it
	if branch_code or branch_name:
		branch_mappings = [
			m for m in branch_mappings 
			if (branch_code and m["bhfid"] == branch_code) or (branch_name and m["branch"] == branch_name)
		]

	for row in branch_mappings:
		branch_bhfid = row["bhfid"]
		branch_name = row["branch"]

		frappe.logger().info(f"[SMART] Registering item {document_name} for branch {branch_name} (bhfId={branch_bhfid})")

		request_data = generate_vsdc_item_payload(
			item_doc.name,
			branch_bhfid,
			settings_name
		)

		route_key = "updateItem" if existing_mapping else "saveItem"

		frappe.enqueue(
			process_request,
			queue="default",
			doctype="Item",
			request_data=request_data,
			route_key=route_key,
			handler_function=handle_registration_response,
			request_method="POST",
			branch=branch_name,
			settings_name=settings_name,
		)


def fetch_matching_items_on_success(response: dict, document_name: str, settings_name: str, bhfid,branch, **kwargs) -> None:
	"""
	Handles Smart Zambia (ZRA) item search response.
	Checks for matching items, archives duplicates if found,
	and registers or creates the ERPNext Item accordingly.
	"""
	from ..apis.api_processor import process_request
	
	frappe.logger().info(f"[SMART] Callback received BHFID: {bhfid}")
	items = parse_response_data(response, list)
	item_doc = frappe.get_doc("Item", document_name)

	# Check for existing mapping
	existing_mapping = next(
		(
			row.zra_item_code
			for row in item_doc.get("custom_smart_setup_mapping", [])
				if row.smart_setup == settings_name
		),
		None,
	)

	# --- CASE 1: Remote items exist ---
	if items:
		if not existing_mapping:
			frappe.get_doc(
				{
					"doctype": "Smart Crystallised Mapping",
					"parent": item_doc.name,
					"parenttype": "Item",
					"parentfield": "custom_smart_setup_mapping",
					"zra_item_code": items[0].get("itemCd"),
					"smart_setup": settings_name,
				}
			).insert(ignore_permissions=True)
			existing_mapping = items[0].get("itemCd")

		# Archive duplicates
		for item in items:
			if existing_mapping != item.get("itemCd"):
				frappe.enqueue(
					process_request,
					queue="default",
					doctype="Item",
					request_data={
						"document_name": item_doc.name,
						"name": f"{item_doc.name} - Archived",
						"itemCd": item.get("itemCd"),
						"useYn": "N",
					},
					route_key="updateItem",
					handler_function=item_archive_on_success,
					request_method="POST",
					settings_name=settings_name,
				)

	# --- CASE 2: No remote item found, trigger new item creation ---
	elif response.get("IsSuccess") is False:
		error_message = response.get("ErrorMessage", "").lower()
		if "no search result" in error_message or "error code: 001" in error_message:
			frappe.logger().info(
				f"[SMART] No existing ZRA item found for {item_doc.name}, creating new item."
			)
			existing_mapping = None 
	
	
	# Trigger registration for all branches
	trigger_item_registration(document_name, settings_name)


def item_archive_on_success(response: dict | None = None, **kwargs):
	"""Placeholder for archive callback"""
	pass
def get_all_branch_mappings(settings_name: str) -> list[dict]:
	"""Return all branch → bhfid mappings from Smart Settings."""
	# settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
	settings =get_settings(settings_name)
	return [
		{
			"branch": row.branch,
			"bhfid": row.branch_code,
			"device_no": row.device_no,
		}
		for row in settings.organisation_mapping
	]
