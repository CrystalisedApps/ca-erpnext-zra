import frappe
from datetime import datetime, timedelta
from ..services.auth_service import ZRAAuthService
from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME

@frappe.whitelist()
def authenticate(settings_name: str):
    """Authenticate with ZRA using username/password and update token in settings."""
    settings_doc = frappe.get_doc(SETTINGS_DOCTYPE_NAME, settings_name)
    needs_update =  not settings_doc.get("jwt") or (
        datetime.strptime(
            str(settings_doc.get("expiry_time")).split(".")[0], "%Y-%m-%d %H:%M:%S"
        )
        < datetime.now()
    )
    if needs_update:
        auth_server_url = settings_doc.server_url
        username = settings_doc.username
        
        password = settings_doc.get_password("password")
       

        token_details = ZRAAuthService.authenticate(
            auth_server_url, username, password,
        )
        if not token_details:
            return None

        settings_doc.jwt = token_details["jwt"]
        settings_doc.expiry_time = datetime.now() + timedelta(
            seconds=token_details["expires_in"]
        )
        settings_doc.save(ignore_permissions=True)
        return settings_doc
   