import frappe
from frappe.model.document import Document


def calculate_tax(doc: "Document") -> None:
    """
    Crystal VSDC: Calculate and assign taxes for invoice items.
    
    Rules:
    - If any item has an Item Tax Template, use item-level taxes.
    - Otherwise, use document-level taxes.
    - Finally, assign the correct Crystal VSDC taxation type codes to each item.
    """
    taxes = doc.get("taxes", [])
    has_item_level_tax = any(getattr(item, "item_tax_template", None) for item in doc.items)

    if has_item_level_tax:
        _calculate_item_level_taxes(doc)
    elif taxes:
        _calculate_document_level_taxes(doc, taxes)

    _set_vsdc_taxation_type_codes(doc)


def _calculate_item_level_taxes(doc: "Document") -> None:
    """
    Apply item-level taxes where tax templates are defined on items.
    """
    for item in doc.items:
        if not item.item_tax_template:
            continue

        # Pull tax rates from the template
        tax_template = frappe.get_doc("Item Tax Template", item.item_tax_template)
        for tax in tax_template.taxes:
            tax_amount = (item.base_net_amount * tax.rate) / 100
            item.base_tax_amount = tax_amount
            item.taxation_type_code = tax.tax_type  # Crystal VSDC mapping


def _calculate_document_level_taxes(doc: "Document", taxes: list) -> None:
    """
    Apply document-level taxes across all items when no item-level template exists.
    """
    for item in doc.items:
        for tax in taxes:
            tax_rate = tax.get("rate", 0)
            tax_amount = (item.base_net_amount * tax_rate) / 100
            item.base_tax_amount = tax_amount
            item.taxation_type_code = tax.get("custom_taxation_type_code")


def _set_vsdc_taxation_type_codes(doc: "Document") -> None:
    """
    Ensure taxation type codes are mapped for Crystal VSDC submission.
    If missing, assign default based on settings or throw an error.
    """
    settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", {"company": doc.company})

    for item in doc.items:
        if not getattr(item, "taxation_type_code", None):
            if settings.default_taxation_type_code:
                item.taxation_type_code = settings.default_taxation_type_code
            else:
                frappe.throw(
                    f"Item {item.item_code} is missing a taxation type code. "
                    "Please configure in settings or item master."
                )
