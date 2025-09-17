import requests
import frappe
from datetime import datetime, timedelta

class ZRAAuthService:
    """Handles authentication with ZRA/Crystal VSDC"""

    AUTH_URL = ""  #  endpoint

    @staticmethod
    def authenticate(settings_name: str) -> str:
        """Authenticate with Crystal VSDC using username & password.
        
        Args:
            settings_name (str): The name of the Crystal ZRA Settings document.
        
        Returns:
            str: The new jwt token.
        """
        settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)

        payload = {
            "username": settings.username,
            "password": settings.get_password("password"),  # stored securely in Frappe
        }

        try:
            response = requests.post(ZRAAuthService.AUTH_URL, json=payload)
            response.raise_for_status()

            data = response.json()
            jwt = data.get("jwt")
            expires_in = data.get("expires_in", 3600)  # seconds, default 1hr

            if not jwt:
                frappe.throw("Authentication failed: No access token in response")

            # Save token + expiry back into settings
            settings.db_set("jwt", jwt)
            expiry_time = datetime.now() + timedelta(seconds=expires_in)
            settings.db_set("token_expiry", expiry_time)

            return jwt

        except requests.RequestException as e:
            frappe.log_error(
                title="Crystal VSDC Authentication Error",
                message=str(e),
                reference_doctype="Crystal ZRA Smart Invoice Settings",
                reference_name=settings_name,
            )
            frappe.throw(f"Failed to authenticate with Crystal VSDC: {e}")

