# ca_erpnext_zra/ca_erpnext_zra/apis/item_api.py

import frappe


def submit_item_composition_on_bom_submit(doc, method):
    """
    Triggered when BOM is submitted.
    Submits all items in the BOM to ZRA (saveItemComposition API).
    """
    branch = doc.custom_smart_branch  # if BOM has branch field
    frappe.enqueue(
        "ca_erpnext_zra.ca_erpnext_zra.apis.item_api.submit_item_composition",
        queue="default",
        timeout=300,
        document_name=doc.name,
        branch=branch
    )
