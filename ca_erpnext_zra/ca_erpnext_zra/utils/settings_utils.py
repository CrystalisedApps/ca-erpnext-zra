import frappe

SETTINGS_DOCTYPE_NAME = "Crystal ZRA Smart Invoice Settings"


def get_settings(settings_name: str | None = None, company: str | None = None) -> dict | None:
    """
    Fetch Crystal ZRA Smart Invoice Settings.

    Priority:
        1. Fetch by settings_name (exact match)
        2. Fetch by company (company_name)
        3. Fallback to first active settings

    Returns:
        dict | None: Settings doc as dict
    """

    # 1. Try fetch using explicit settings name
    if settings_name:
        try:
            if frappe.db.exists(SETTINGS_DOCTYPE_NAME, settings_name):
                return frappe.get_doc(SETTINGS_DOCTYPE_NAME, settings_name).as_dict()
        except Exception:
            pass

    # 2. Try fetch using company name
    if company:
        settings_by_company = frappe.get_all(
            SETTINGS_DOCTYPE_NAME,
            filters={"company_name": company, "is_active": 1},
            fields=["name"],
            limit=1,
        )
        if settings_by_company:
            return frappe.get_doc(SETTINGS_DOCTYPE_NAME, settings_by_company[0].name).as_dict()

    # 3. Fallback → first active settings
    settings = frappe.get_all(
        SETTINGS_DOCTYPE_NAME,
        filters={"is_active": 1},
        fields=["name"],
        limit=1,
    )
    if settings:
        return frappe.get_doc(SETTINGS_DOCTYPE_NAME, settings[0].name).as_dict()

    return None



def get_server_url(
	company_name: str | None = None,
	branch_id: str | None = "00",
	settings_name: str | None = None,
) -> str | None:
	"""
	Fetch the Crystal VSDC server URL from ZRA Settings.
	"""
	settings = get_settings(settings_name)

	if settings:
		return settings.get("server_url")

	return None
