import frappe
import json
from typing import Any, Dict, List, Union



@frappe.whitelist()
def get_smart_action_data(doctype: str, docname: str = None) -> dict[str, Any]:
    """Return Smart Zambia settings and item registration status (single setup only)."""
    active_settings = get_active_smart_settings()

    # No specific doc → just return available settings
    if not docname:
        return {
            "settings": active_settings,
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

 
    is_registered = bool(
        doc.get("custom_item_registered")  
        
    )

    registered_mappings = active_settings if is_registered else []
    unregistered_settings = [] if is_registered else active_settings

    return {
        "settings": active_settings,
        "registered": is_registered,  
        "has_mappings": is_registered,
        "registered_mappings": registered_mappings,
        "unregistered_settings": unregistered_settings,
    }



def get_active_smart_settings() -> list[dict]:
    """Return the single active Smart Zambia settings record using get_all."""
    # Just fetch the first record since this is a single-setup
    settings = frappe.get_all("Crystal ZRA Smart Invoice Settings", fields=["name","company_name","tpin", "server_url"])

    if not settings:
        return []

    s = settings[0]
    return [{
        "name": s["name"],
        "company": s.get("company_name") or frappe.defaults.get_global_default("company"),
        "tpin": s.get("tpin"),
        "bhfId": "000",
        "api_url": s.get("server_url"),
        "is_valid": True,
    }]

