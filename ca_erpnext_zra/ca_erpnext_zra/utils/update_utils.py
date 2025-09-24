import frappe
from frappe.model.document import Document
from typing import List, Dict, Any, Optional, Union, Callable

def update_documents(
    data: List[Dict[str, Any]],
    doctype: str,
    field_mapping: Dict[str, Union[str, tuple[str, Callable[[Dict[str, Any]], Any]]]],
    unique_key: Optional[str] = None,
    parent: str = None,
    parenttype: str = None,
    parentfield: str = None,
    return_docs: bool = False,
) -> List[Document] | None:
    """
    Generic helper to insert or update documents from API responses.

    field_mapping supports two formats:
      - {"api_field": "doctype_field"}
      - {"api_field": ("doctype_field", lambda entry: computed_value)}

    Example:
        {
            "itemClsCd": "item_cls_cd",
            "useYn": ("is_used", lambda x: 1 if str(x.get("useYn", "")).upper() == "Y" else 0)
        }
    """
    if not data:
        return []

    saved_docs = []

    for entry in data:
        lookup_value = entry.get(unique_key) if unique_key else None

        # Try to find existing doc if unique_key provided
        if unique_key and lookup_value:
            key_field = (
                field_mapping.get(unique_key, unique_key)
                if isinstance(field_mapping.get(unique_key), str)
                else unique_key
            )
            existing_doc_name = frappe.get_value(doctype, {key_field: lookup_value})
        else:
            existing_doc_name = None

        doc: Document = (
            frappe.get_doc(doctype, existing_doc_name)
            if existing_doc_name
            else frappe.new_doc(doctype)
        )

        # Map fields
        for api_field, mapping in field_mapping.items():
            if isinstance(mapping, str):
        # direct mapping
                try:
                    raw_val = entry.get(api_field)
                    doc.set(mapping, raw_val)
                except Exception as e:
                    frappe.log_error(
                        f"Error applying function mapping for field {api_field}: {e}\nEntry: {entry}",
                        "update_documents lambda error"
                    )

            elif isinstance(mapping, tuple) and callable(mapping[1]):
                target_field, fn = mapping
                try:
                    doc.set(target_field, fn(entry.get(api_field)))
                except Exception as e:
                    frappe.log_error(
                        f"Error applying function mapping for field {api_field}: {e}\nEntry: {entry}",
                        "update_documents lambda error"
                    )
            else:
                frappe.log_error(
                    f"Invalid mapping for field {api_field}: {mapping}",
                    "update_documents field_mapping error",
                )


        # Handle parent linkage for child tables
        if parent and parenttype and parentfield:
            doc.parent = parent
            doc.parenttype = parenttype
            doc.parentfield = parentfield

        doc.save(ignore_permissions=True)
        saved_docs.append(doc)

    frappe.db.commit()
    return saved_docs if return_docs else None
