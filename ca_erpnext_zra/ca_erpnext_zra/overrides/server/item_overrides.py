import frappe
from frappe.model.document import Document
from ...apis.item_api import perform_item_registration
from ...utils.payload_utils import generate_custom_item_code_smart

def on_item_update(doc, method=None):
	# Call your whitelisted function safely with item name
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

    if doc.custom_prevent_smart_registration != 1:
        missing_fields = []
        if not doc.custom_smart_country_of_origin_:
            missing_fields.append("Country of Origin Code")
        if not doc.custom_smart_item_type:
            missing_fields.append("Product Type")
        if not doc.custom_smart_packaging_unit:
            missing_fields.append("Packaging Unit Code")
        if not doc.custom_smart_quantity_unit:
            missing_fields.append("Unit of Quantity Code")
        if not doc.custom_smart_item_classification_code:
            missing_fields.append("Item Classification")
        if not doc.custom_vat_category_code:
            missing_fields.append("Taxation Type")

        if missing_fields:
            frappe.throw(_("Please fill in the following required fields: {0}").format(", ".join(missing_fields)))

    if not doc.custom_smart_item_code:
        doc.custom_item_code_etims = generate_custom_item_code_smart(doc)
