from datetime import datetime
import frappe
from frappe import _

from .settings_utils import get_settings
from ..apis.auth import authenticate  # refreshes token and updates settings


def build_headers(company_name: str, branch_id: str, settings_name: str = None) -> dict[str, str] | None:
    """
    Build headers for Crystal Smart Invoice API requests.
    Ensures access token is valid; refreshes if expired.

    Args:
        company_name (str): The company name.
        branch_id (str, optional): The branch ID.
        settings_name (str, optional): The ZRA Settings docname.

    Returns:
        dict[str, str] | None: The headers including Authorization, Device ID, etc.
    """
    settings = get_settings(company_name, branch_id, settings_name)

    if not settings:
        return None

    jwt = settings.get("jwt")
    token_expiry = settings.get("token_expiry")

    # Check if token is missing or expired
    if (
        not jwt
        or not token_expiry
        or (
            datetime.strptime(str(token_expiry).split(".")[0], "%Y-%m-%d %H:%M:%S")
            < datetime.now()
        )
    ):
        # Call authenticate → refresh token and update settings
        auth_response = authenticate(settings.name)

        if not auth_response or not auth_response.get("access_token"):
            frappe.throw(
                _("Failed to refresh Crystal VSDC token. Please check your ZRA Settings."),
                frappe.AuthenticationError,
            )

        # Use new token directly from updated settings
        settings.reload()
        access_token = settings.get("jwt")

    # Build base headers
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Attach device_id if available
    # device_id = settings.get("device_id")
    # if device_id:
    #     headers["Device-Id"] = device_id

    # Attach TIN if available
    # taxpayer_pin = settings.get("taxpayer_pin")
    # if taxpayer_pin:
    #     headers["TIN"] = taxpayer_pin

    return headers
