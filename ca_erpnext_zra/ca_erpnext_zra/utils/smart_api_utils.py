import frappe
from typing import Any


@frappe.whitelist()
def get_smart_action_data(doctype: str, docname: str = None) -> dict[str, Any]:
    """
    Return Smart Zambia settings and item registration status for multi-company setups.
    """

    active_settings = get_active_smart_settings()

    # If no Smart settings exist at all
    if not active_settings:
        return {
            "settings": [],
            "registered": False,
            "has_mappings": False,
            "registered_mappings": [],
            "unregistered_settings": [],
        }

    # If docname not provided, just return list of available setups
    if not docname:
        return {
            "settings": active_settings,
            "registered": False,
            "has_mappings": False,
            "registered_mappings": [],
            "unregistered_settings": active_settings,
        }

    try:
        doc = frappe.get_doc(doctype, docname)
    except Exception:
        return {
            "settings": active_settings,
            "registered": False,
            "has_mappings": False,
            "registered_mappings": [],
            "unregistered_settings": active_settings,
        }

    # --- Determine existing mappings (multi-company aware) ---
    registered_mappings = []
    if hasattr(doc, "smart_setup_mapping"):
        # If you have a mapping child table
        for row in doc.smart_setup_mapping:
            registered_mappings.append({
                "smart_setup": row.smart_setup,
                "smart_item_id": row.smart_item_id or "",
                "company": frappe.db.get_value(
                    "Crystal ZRA Smart Invoice Settings",
                    row.smart_setup,
                    "company_name"
                ),
            })
    else:
        # Fallback to single flag
        if doc.get("custom_item_registered"):
            registered_mappings = active_settings

    registered_setup_names = [r["smart_setup"] for r in registered_mappings if r.get("smart_setup")]
    unregistered_settings = [
        s for s in active_settings if s["name"] not in registered_setup_names
    ]

    is_registered_any = bool(registered_mappings)

    return {
        "settings": active_settings,
        "registered": is_registered_any,
        "has_mappings": is_registered_any,
        "registered_mappings": registered_mappings,
        "unregistered_settings": unregistered_settings,
    }


@frappe.whitelist()
def get_active_smart_settings() -> list[dict]:
    """
    Return all active Smart Zambia settings records (multi-company).
    Each record represents a company setup.
    """
    settings = frappe.get_all(
        "Crystal ZRA Smart Invoice Settings",
        filters={"is_active": 1},
        fields=["name", "company_name", "tpin", "server_url"]
    )

    if not settings:
        return []

    active_settings = []
    for s in settings:
        active_settings.append({
            "name": s["name"],
            "company": s.get("company_name") or frappe.defaults.get_global_default("company"),
            "tpin": s.get("tpin"),
            "bhfId": "000",  # Default branch ID; can be replaced by real value
            "api_url": s.get("server_url"),
            "is_valid": True,
        })

    return active_settings


def split_user_email(email_string: str) -> str:
    """Retrieve portion before @ from an email string"""
    return email_string.split("@")[0]