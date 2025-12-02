import frappe
from frappe.model.document import Document
from ...apis.item_api import perform_item_registration
from ...utils.payload_utils import generate_custom_item_code_smart

def on_item_update(doc, method=None):
	perform_item_registration(doc.name)


def validate(doc: Document, method: str = None) -> None:
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

    