import frappe
from ...apis.item_api import perform_item_registration

def on_item_update(doc, method=None):
    # Call your whitelisted function safely with item name
    perform_item_registration(doc.name)