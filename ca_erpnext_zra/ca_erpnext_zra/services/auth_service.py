import requests
import frappe
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

from frappe.integrations.utils import create_request_log

from ..doctype.doctype_names_mapping import SETTINGS_DOCTYPE_NAME


class ZRAAuthService:
    """Handles authentication with ZRA/Crystal VSDC"""

    

    @staticmethod
    def authenticate(
       
        auth_server_url: str,
        username: str,
        password: str,
        docname: str = None,
        ) -> dict:
        """Authenticate with Crystal VSDC using username & password.
        
        Args:
            settings_name (str): The name of the Crystal ZRA Settings document.
        
        Returns:
            str: The new jwt token.
        """
        AUTH_URL = f"{auth_server_url}/api/v1/Users/GetToken"
      

        payload = {
            "username": username,
            "password": password
        }
        headers = {
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            }

        integration_request = create_request_log(
                data=json.dumps(payload),
                request_description="Crystal VSDC Authentication",
                is_remote_request=True,
                service_name="Crystal VSDC Authentication",
                request_headers=json.dumps(headers),
                url=AUTH_URL,
                reference_doctype=SETTINGS_DOCTYPE_NAME,
                reference_docname=docname,
            )
        try:
            response = requests.post(AUTH_URL, json=payload)
            frappe.db.set_value("Integration Request", integration_request.name, "output", response.text, update_modified=False)
            
            response.raise_for_status()
            if response.ok:
                data = response.json()
                frappe.db.set_value("Integration Request", integration_request.name, "status", "Completed", update_modified=False)
                expires_in = (data.get("expires_in") or 3600)
                expiry_time = datetime.now() + timedelta(seconds=int(expires_in))
                return {
                "jwt": data.get("token"),
                    "expires_in": int(expires_in),
                    "expiry_time": expiry_time.strftime("%Y-%m-%d %H:%M:%S"),            }
            error = response.json().get("error", "Unknown error") if response.headers.get("content-type", "").startswith("application/json") else "Invalid response"
            frappe.db.set_value("Integration Request", integration_request.name, "status", "Failed", update_modified=False)
            frappe.db.set_value("Integration Request", integration_request.name, "error", error, update_modified=False)
            frappe.throw(f"Authentication failed: <b>{error}</b>")

        except Exception as e:
            frappe.db.set_value("Integration Request", integration_request.name, {
                "status": "Failed",
                "error": str(e)
            }, update_modified=False)
            frappe.throw(f"Authentication request failed: <b>{e}</b>")


