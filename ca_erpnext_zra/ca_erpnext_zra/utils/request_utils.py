import json
import frappe

def parse_request_data(request_data: str | dict | None) -> dict:
    """
    Normalize incoming request_data into a Python dict.
    Used before sending data to Crystal Smart Invoice APIs.

    Args:
        request_data (str | dict | None): The request data provided
            by client code (Form, API, Scheduler, etc.)

    Returns:
        dict: Parsed request data
    """
    if not request_data:
        return {}

    if isinstance(request_data, str):
        try:
            return json.loads(request_data)
        except json.JSONDecodeError:
            frappe.throw("Invalid JSON string provided for request_data.")

    if isinstance(request_data, (dict,list)):
        return request_data

    return {}
