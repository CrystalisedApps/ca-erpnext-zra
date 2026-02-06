from typing import Callable

import frappe
import frappe.defaults

from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME
from ..utils.headers_utils import build_headers
from ..utils.request_utils import parse_request_data
from ..utils.routes_utils import get_route_path
from ..utils.settings_utils import get_server_url, get_settings
from ..utils.url_utils import process_dynamic_url
from .api_builder import EndpointsBuilder

# Initialize once
endpoints_builder = EndpointsBuilder()


def process_request(
	request_data: str | dict,
	route_key: str,
	handler_function: Callable = None,
	request_method: str = "GET",
	doctype: str = SETTINGS_DOCTYPE_NAME,
	error_callback: Callable = None,
	settings_name: str = None,
	company: str = None,
    bhfid=None,
	branch=None,

	document_name: str = None,
) -> str | dict | None:
	"""
	Core request processor for Crystal Smart Invoice servers.

	Handles preparation of headers, server URL, and route path,
	then delegates to `execute_request` for remote API interaction.
	"""

	# frappe.throw(str(settings_name))
	# --- NEW fallback handling ---
	settings = get_settings(settings_name)

	if not settings:
		frappe.throw(
			"No active Smart API Settings found. Please configure one in Crystal ZRA Smart Invoice Settings."
		)

	# Normalized settings_name (always resolved now)
	settings_name = settings.get("name")

	# Normalize and parse incoming request data
	data = parse_request_data(request_data)
	extracted_company, branch_id, extracted_docname = extract_metadata(data)
	document_name = document_name or extracted_docname
	company_name = (
		company
		or extracted_company
		or frappe.defaults.get_user_default("Company")
		or frappe.get_value("Company", {}, "name")
	)

	# Build request headers and URL
	headers = build_headers(settings_name)
	server_url = get_server_url(company_name, branch_id, settings_name)

	# Resolve route from key (specific to ZRA VSDC)
	route_path, _ = get_route_path(route_key, "Crystal VSDC")
	if not route_path:
		frappe.throw(f"Route not found for key: {route_key}. Please ensure it is configured in the Crystal ZRA Route DocType for vendor 'Crystal VSDC'.")
	dynamic_route_path = process_dynamic_url(route_path, request_data)
	url = f"{server_url}{dynamic_route_path}"

	settings = get_settings(settings_name)
	if not settings:
		return

	if headers and server_url and route_path:
		return execute_request(
			headers,
			url,
			route_path,
			data,
			route_key,
			handler_function,
			request_method,
			doctype,
			document_name,
			error_callback,
			settings,
			bhfid=bhfid,
			branch=branch
		)
	else:
		return f"Failed to process {route_key}. Missing required configuration."


# def add_organisation_branch_department(settings: dict) -> dict:
#     """
#     Optional helper for enriching request payloads
#     with organisation/branch/department identifiers.
#     """
#     organisation = settings.get("company")
#     branch = settings.get("bhfid")
#     source_organisation = settings.get("department")

#     result = {}
#     if organisation:
#         result["organisation"] = get_link_value(
#             "Company", "name", organisation, "custom_zra_id"
#         )
#     if branch:
#         result["branch"] = get_link_value("Branch", "name", branch, "zra_id")
#     if source_organisation:
#         result["source_organisation_unit"] = get_link_value(
#             "Department", "name", source_organisation, "custom_zra_id"
#         )

#     return result


def extract_metadata(data: dict) -> tuple:
	"""
	Extracts company, branch, and document metadata
	from request payload.
	"""
	if isinstance(data, list) and data:
		first_entry = data[0]
		company_name = (
			first_entry.get("company")
			or first_entry.get("company_name")
			or frappe.defaults.get_user_default("Company")
			or frappe.get_value("Company", {}, "name")
		)
		branch_id = (
			first_entry.get("branch_id")
			or frappe.defaults.get_user_default("Branch")
			or frappe.get_value("Branch", "name")
		)
		document_name = first_entry.get("document_name", None)

	else:
		company_name = (
			data.pop("company", None)
			or data.pop("company_name", None)
			or frappe.defaults.get_user_default("Company")
			or frappe.get_value("Company", {}, "name")
		)
		branch_id = (
			data.pop("branch_id", None)
			or frappe.defaults.get_user_default("Branch")
			or frappe.get_value("Branch", "name")
		)
		document_name = data.pop("document_name", None)
	return company_name, branch_id, document_name


def clean_data_for_get_request(data: dict) -> None:
	"""Remove fields not required for GET requests."""
	if "document_name" in data and data["document_name"]:
		data.pop("document_name")
	if "company_name" in data and data["company_name"]:
		data.pop("company_name")


def execute_request(
	headers: dict,
	url: str,
	route_path: str,
	data: dict,
	route_key: str,
	handler_function: Callable,
	request_method: str,
	doctype: str,
	document_name: str,
	error_callback: Callable = None,
	settings: dict = None,
	bhfid: str | None = None,
	branch: str | None =None
	
) -> str | dict | None:
	"""
	Executes a remote call against Crystal VSDC.

	Handles:
	  - GET/POST payload normalization
	  - Pagination via 'next' URLs
	  - Success/error callbacks
	"""
	if request_method == "GET":
		clean_data_for_get_request(data)

	last_response_data = None

	while url:
		endpoints_builder.headers = headers
		endpoints_builder.url = url
		endpoints_builder.route_path = route_path
		endpoints_builder.payload = data
		endpoints_builder.request_description = route_key
		endpoints_builder.method = request_method
		endpoints_builder.success_callback = handler_function
		endpoints_builder.error_callback = error_callback
		endpoints_builder.settings = settings

		response = endpoints_builder.make_remote_call(
			doctype=doctype,
			document_name=document_name,
			 bhfid=bhfid,
			 branch=branch
		)

		if isinstance(response, dict) and "next" in response and response.get("next") != url:
			url = response["next"]
			last_response_data = response
		else:
			last_response_data = response
			url = None

	return last_response_data
