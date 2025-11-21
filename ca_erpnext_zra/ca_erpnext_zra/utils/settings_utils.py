import frappe

SETTINGS_DOCTYPE_NAME = "Crystal ZRA Smart Invoice Settings"


def get_settings(settings_name: str | None = None) -> dict | None:
	"""Fetch Crystal ZRA Smart Invoice integration settings.

	- If settings_name is given and valid → return that doc
	- Otherwise, return the first active settings
	"""

	# If a specific settings doc is requested
	if settings_name:
		try:
			if frappe.db.exists(SETTINGS_DOCTYPE_NAME, settings_name):
				return frappe.get_doc(SETTINGS_DOCTYPE_NAME, settings_name).as_dict()
		except Exception:
			pass  # fall through to fallback

	# Otherwise → fallback to first active settings
	settings = frappe.get_all(
		SETTINGS_DOCTYPE_NAME,
		filters={"is_active": 1},
		fields=["name", "company_name", "tpin", "server_url", "sales_auto_submission_enabled"],
		limit=1,
	)

	if settings:
		return settings[0]

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
