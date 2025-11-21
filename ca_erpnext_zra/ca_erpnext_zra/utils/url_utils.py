import json
import re

import frappe
from frappe import _


def process_dynamic_url(route_path: str, request_data: dict | str) -> str:
	"""
	Replace placeholders in the route_path with values from request_data.
	Used for building dynamic URLs for Crystal VSDC endpoints.

	Args:
	    route_path (str): A URL template that may include placeholders,
	                      e.g. "/invoices/{invoiceId}/items"
	    request_data (dict | str): Data containing values to fill in placeholders

	Returns:
	    str: The route_path with placeholders substituted with actual values

	Raises:
	    ValueError: If request_data is malformed or missing a required placeholder
	"""
	# If request_data is a JSON string, parse it
	if isinstance(request_data, str):
		try:
			request_data = json.loads(request_data)
		except json.JSONDecodeError as e:
			frappe.log_error(title="Dynamic URL Error", message=str(e))
			raise ValueError(_("Invalid JSON string in request_data.")) from e

	# Find all placeholder names of the form {placeholder}
	placeholders = re.findall(r"\{(.*?)\}", route_path)
	for placeholder in placeholders:
		if placeholder in request_data:
			# Convert the value to string and replace
			route_path = route_path.replace(f"{{{placeholder}}}", str(request_data[placeholder]))
		else:
			frappe.log_error(
				title="Dynamic URL Error",
				message=f"Missing required placeholder '{placeholder}' in request_data for URL '{route_path}'",
			)
			raise ValueError(_("Missing required placeholder: '{0}'").format(placeholder))

	return route_path
