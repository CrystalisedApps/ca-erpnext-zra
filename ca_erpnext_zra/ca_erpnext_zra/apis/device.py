import frappe
from frappe.utils.password import get_decrypted_password

from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME
from .api_processor import process_request
from ..utils.settings_utils import get_settings

@frappe.whitelist()
def initialize_device(settings_name: str = None, branch: str=None) -> dict:
	"""
	Initialize a device with Crystal VSDC servers.

	Endpoint:
	    POST /api/v1/InitializationInfo/SelectInitInfo

	Args:
	    request_data (str | dict): JSON string or dict with keys:
	        - tpin (str): Taxpayer Identification Number
	        - bhfId (str): Branch ID
	        - dvcSrlNo (str): Device Serial Number
	    settings_name (str, optional): Crystal ZRA Smart Invoice Settings docname.

	Returns:
	    dict: Response from Crystal VSDC.
	"""
	if not branch:
		frappe.throw("Branch is required for device initialization")
	branch_doc = frappe.get_doc("Branch", branch)
	branch_code = branch_doc.get("custom_branch_code")
	device_serial = branch_doc.get("custom_smart_device_serial_no")
	if not branch_code:
		frappe.throw(f"Branch '{branch}' is missing Branch Code (custom_branch_code)")

	if not device_serial:
		frappe.throw(f"Branch '{branch}' is missing Device Serial Number (custom_device_serial_no)")

	settings = get_settings(settings_name)

	tpin = settings.get("tpin")
	request_data = {
		"tpin": tpin,
		"bhfId": branch_code,
		"dvcSrlNo": device_serial or f"{tpin}_VSDC",
	}

	if not request_data:
		frappe.throw("Request data required for device initialization")
	return process_request(
		request_data=request_data,
		route_key="selectInitInfo",
		handler_function=initialize_device_on_success,
		request_method="POST",
		doctype=SETTINGS_DOCTYPE_NAME,
		settings_name=settings_name,
        branch=branch
	)


def initialize_device_on_success(response: dict, settings_name=None, branch=None, **kwargs) -> dict:
    result = response.get("Result", {})
    result_cd = result.get("resultCd")
    bhfId = result.get("bhfId")

    # Message handling...
    if result_cd == "902":
        frappe.msgprint("ℹ Device already initialized with Crystal VSDC")
    elif result_cd == "000":
        frappe.msgprint(" Successfully initialized device with Crystal VSDC")
    else:
        frappe.msgprint(" Device initialization successful with Crystal VSDC")

    # --- Save mapping ---
    if settings_name and branch:
        branch_doc = frappe.get_doc("Branch", branch)

        parent = settings_name
        parenttype = "Crystal ZRA Smart Invoice Settings"
        parentfield = "organisation_mapping"

        exists = frappe.db.exists(
            "Smart Settings Organisation Mapping",
            {"parent": parent, "branch": branch}
        )

        if exists:
            frappe.db.set_value("Smart Settings Organisation Mapping", exists, {
                "branch_code": branch_doc.custom_branch_code,
                "device_no": branch_doc.custom_smart_device_serial_no,
            })
        else:
            frappe.get_doc({
                "doctype": "Smart Settings Organisation Mapping",
                "parent": parent,
                "parenttype": parenttype,
                "parentfield": parentfield,
                "branch": branch,
                "branch_code": branch_doc.custom_branch_code,
                "device_no": branch_doc.custom_smart_device_serial_no,
            }).insert(ignore_permissions=True)

    return response
