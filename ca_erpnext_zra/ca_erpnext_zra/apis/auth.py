import frappe
from ca_erpnext_zra.ca_erpnext_zra.services.auth_service import ZRAAuthService

@frappe.whitelist()
def authenticate(settings_name: str):
    """Authenticate with ZRA using username/password and update token in settings."""
    token = ZRAAuthService.authenticate(settings_name)
    return {
        "status": "success",
        "jwt": token
    }
