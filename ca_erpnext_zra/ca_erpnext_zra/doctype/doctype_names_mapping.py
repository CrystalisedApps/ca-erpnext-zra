# Copyright (c) 2025, Brian Mwambia
# For license information, please see license.txt

"""
Centralized mapping for all DocType names used in the ZRA VSDC integration.
Using constants avoids hardcoding DocType strings throughout the codebase.
"""

# Core Crystal ZRA DocTypes
SETTINGS_DOCTYPE_NAME = "Crystal ZRA Smart Invoice Settings"              # Holds credentials, URLs, tokens
ROUTES_TABLE_CHILD_DOCTYPE_NAME = "Crystal Smart Invoice Route Item"
ROUTES_TABLE_DOCTYPE_NAME = "Crystal Smart Invoice Routes"

TAXATION_TYPE_DOCTYPE_NAME="Crystal ZRA Smart Invoice Taxation Type"
ITEM_CLASSIFICATIONS_DOCTYPE_NAME = "Crystal ZRA Smart Invoice Item Classification"

REGISTERED_PURCHASES_DOCTYPE_NAME="Crystallised ZRA Smart Purchases"