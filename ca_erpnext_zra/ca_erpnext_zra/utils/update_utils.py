import frappe
from frappe.model.document import Document


def update_documents(
    doctype: str,
    data: list[dict],
    unique_key: str,
    field_mapping: dict[str, str],
) -> None:
    """
    Generic helper to insert or update documents from API responses.

    Args:
        doctype (str): Target ERPNext doctype (e.g. "ZRA Country").
        data (list[dict]): API response payload (list of dicts).
        unique_key (str): Field in API data used to identify unique records.
        field_mapping (dict[str, str]): Mapping {api_field: doctype_field}.
    """
    if not data:
        return

    for entry in data:
        lookup_value = entry.get(unique_key)
        if not lookup_value:
            continue

        # Try find existing doc
        existing_doc_name = frappe.get_value(
            doctype,
            {field_mapping.get(unique_key, unique_key): lookup_value}
        )

        if existing_doc_name:
            doc: Document = frappe.get_doc(doctype, existing_doc_name)
        else:
            doc: Document = frappe.new_doc(doctype)

        # Map fields
        for api_field, doc_field in field_mapping.items():
            doc.set(doc_field, entry.get(api_field))

        doc.save(ignore_permissions=True)

    frappe.db.commit()
