import frappe
from frappe.model.document import Document
from typing import List, Dict, Any, Optional

def update_documents(
    data: List[Dict[str, Any]],
    doctype: str,
    field_mapping: Dict[str, str],
    unique_key: Optional[str] = None,
    parent: str = None,
    parenttype: str = None,
    parentfield: str = None,
    return_docs: bool = False,
) -> List[Document] | None:
    """
    Generic helper to insert or update documents from API responses.

    Args:
        data (list[dict]): API response payload (list of dicts).
        doctype (str): Target ERPNext doctype (e.g. "Crystal VSDC Codes").
        field_mapping (dict): Mapping {api_field: doctype_field}.
        unique_key (str, optional): Field in API data used to identify unique records.
        parent/parenttype/parentfield (str, optional): For child tables.
        return_docs (bool): If True, return list of saved docs.

    Returns:
        list[Document] | None: List of docs if return_docs=True, else None
    """
    if not data:
        return []

    saved_docs = []

    for entry in data:
        lookup_value = entry.get(unique_key) if unique_key else None

        # Try to find existing doc if unique_key provided
        if unique_key and lookup_value:
            existing_doc_name = frappe.get_value(
                doctype,
                {field_mapping.get(unique_key, unique_key): lookup_value}
            )
        else:
            existing_doc_name = None

        if existing_doc_name:
            doc: Document = frappe.get_doc(doctype, existing_doc_name)
        else:
            doc: Document = frappe.new_doc(doctype)

        # Map fields
        for api_field, doc_field in field_mapping.items():
            doc.set(doc_field, entry.get(api_field))

        # If this is a child record, attach parent metadata
        if parent and parenttype and parentfield:
            doc.parent = parent
            doc.parenttype = parenttype
            doc.parentfield = parentfield

        doc.save(ignore_permissions=True)
        saved_docs.append(doc)

    frappe.db.commit()
    return saved_docs if return_docs else None
