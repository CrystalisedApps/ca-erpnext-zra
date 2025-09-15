import frappe

SETTINGS_DOCTYPE_NAME = "Crystal ZRA Smart Invoice Settings"


def get_settings(settings_name: str = None) -> dict | None:
    """Fetch ZRA integration settings.

    Args:
        settings_name (str, optional): The name of the Crystal ZRA Smart Invoice Settings document.
            If not provided, will return the first active settings record.

    Returns:
        dict | None: The settings if found, otherwise None.
    """
    # If a specific settings document is given
    if settings_name:
        if frappe.db.exists(SETTINGS_DOCTYPE_NAME, {"name": settings_name}):
            return frappe.get_doc(SETTINGS_DOCTYPE_NAME, settings_name).as_dict()
        return None

    # Otherwise, fetch the active ZRA Settings
    if frappe.db.exists(SETTINGS_DOCTYPE_NAME, {"is_active": 1}):
        return frappe.get_value(
            SETTINGS_DOCTYPE_NAME,
            {"is_active": 1},
            "*",
            as_dict=True,
        )

    return None


def get_server_url(company_name: str = None, branch_id: str = "00", settings_name: str = None) -> str | None:
    """
    Fetch the Crystal VSDC server URL from ZRA Settings.

    Args:
        company_name (str, optional): Company linked to the ZRA Settings.
        branch_id (str, optional): Branch identifier (default "00").
        settings_name (str, optional): Specific Crystal ZRA Smart Invoice Settings document to use.

    Returns:
        str | None: The base server URL if available, otherwise None.
    """
    settings = get_settings(settings_name)

    if settings:
        return settings.get("server_url")

    return None
