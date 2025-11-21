import frappe

from ..utils.payload_utils import generate_vsdc_item_payload
from ..utils.response_utils import parse_response_data


def handle_registration_response(
	response,
	request_data=None,
	document_name=None,
	doctype=None,
	payload=None,
	settings_name=None,
):
	"""
	Handles ZRA Smart Invoice item registration (POST/PATCH) response.
	Links the registered itemCd to local Item via Smart Crystallised Mapping.
	"""
	frappe.logger().info(f"[SMART] Registration Response: {frappe.as_json(response)}")

	try:
		# Safely unpack ZRA response
		is_success = response.get("IsSuccess")
		result = response.get("Result") or {}
		result_cd = result.get("resultCd")
		result_data = result.get("data") or {}

		# Proceed only on successful registration
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

			# Find corresponding ERPNext Item
			item_name = frappe.db.get_value("Item", {"item_code": item_code}, "name")
			if not item_name:
				frappe.log_error(f"[SMART] Item with code {item_code} not found", "Registration Handler")
				return

			# Extract ZRA item code (fallback to item_code)
			zra_item_code = result_data.get("itemCd") or result.get("ItemCd") or item_code

			# Update or append Smart Crystallised Mapping
			item_doc = frappe.get_doc("Item", item_name)
			found = False

			for row in item_doc.get("custom_smart_setup_mapping", []):
				if row.smart_setup == settings_name:
					frappe.db.set_value(
						"Smart Crystallised Mapping",
						row.name,
						{"zra_item_code": zra_item_code},
					)
					found = True
					break

			if not found:
				item_doc.append(
					"custom_smart_setup_mapping",
					{
						"smart_setup": settings_name,
						"zra_item_code": zra_item_code,
					},
				)
				item_doc.save(ignore_permissions=True)

			# Mark as registered
			frappe.db.set_value("Item", item_name, "custom_item_registered", 1)
			frappe.db.commit()

			frappe.logger().info(f"[SMART] Registered: {item_code} → ZRA Code: {zra_item_code}")

			# # Enqueue inventory sync if applicable
			# if getattr(item_doc, "is_stock_item", False):
			#     frappe.enqueue(
			#         "ca_erpnext_zra.ca_erpnext_zra.apis.item_api.submit_inventory",
			#         item_name=item_name,
			#         queue="long",
			#     )

		else:
			frappe.log_error(
				title="[SMART] Registration Failed",
				message=f"Response: {frappe.as_json(response)}\nPayload: {payload}",
			)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"[SMART] Failed to process registration response: {e}")


def fetch_matching_items_on_success(response: dict, document_name: str, settings_name: str, **kwargs) -> None:
	"""
	Handles Smart Zambia (ZRA) item search response.
	Checks for matching items, archives duplicates if found,
	and registers or creates the ERPNext Item accordingly.
	"""
	from ..apis.api_processor import process_request

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
			existing_mapping = None  # explicitly set to None to trigger creation

	# --- Build payload for registration/update ---
	request_data = generate_vsdc_item_payload(item_doc.name, settings_name)

	# Decide route key based on existing mapping
	route_key = "updateItem" if existing_mapping else "saveItem"

	frappe.enqueue(
		process_request,
		queue="default",
		doctype="Item",
		request_data=request_data,
		route_key=route_key,
		handler_function=handle_registration_response,
		request_method="POST",
		settings_name=settings_name,
	)


def item_archive_on_success(response: dict | None = None, **kwargs):
	"""Placeholder for archive callback"""
	pass
