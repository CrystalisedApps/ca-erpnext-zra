import frappe
from frappe.model.document import Document
from ...apis.item_api import perform_item_registration
from ...utils.payload_utils import generate_custom_item_code_smart
from ...utils.smart_api_utils import get_active_smart_settings

def on_update(doc, method=None):
    # Get all active Smart API settings
    active_settings = get_active_smart_settings()
    
    if not active_settings:
        return

    for setting in active_settings:
        # Get all branch mappings for this setup
        mapped_branches = frappe.get_all(
            "Smart Settings Organisation Mapping",
            filters={"parent": setting["name"] },
            fields=["branch", "branch_code"]
        )
        # frappe.throw(str(setting))
        for branch_row in mapped_branches:
            # Check if this item already has a mapping for this setup + branch
            exists = frappe.db.exists(
                "Smart Crystallised Mapping",
                {
                    "parent": doc.name,
                    "smart_setup": setting["name"],
                    "branch": branch_row.branch
                }
            )

            if not exists and not frappe.flags.in_item_registration:
                # Pass branch and branch_code to registration
                frappe.flags.in_item_registration = True
                perform_item_registration(
                    doc=doc,
                    settings_name=setting.get("name") ,
                    branch=branch_row.branch,
                    branch_code=branch_row.branch_code
                )


def validate(doc: Document, method: str = None) -> None:
    if not doc.custom_vat_category_code:
        return  # nothing to do
    is_tax_type_changed = doc.has_value_changed("custom_vat_category_code")
    if doc.custom_vat_category_code and is_tax_type_changed:
        relevant_tax_templates = frappe.get_all(
            "Item Tax Template",
            ["*"],
            {"custom_taxation_type": doc.custom_vat_category_code},
        )

        if relevant_tax_templates:
            doc.set("taxes", [])
            for template in relevant_tax_templates:
                doc.append("taxes", {"item_tax_template": template.name})

    