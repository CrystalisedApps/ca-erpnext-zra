import frappe
import json
from frappe.model.document import Document

from ..doctype.doctype_names_mapping import (
    COUNTRIES_DOCTYPE_NAME,
    UNIT_OF_QUANTITY_DOCTYPE_NAME,
    PACKAGING_UNIT_DOCTYPE_NAME,
ITEM_CLASSIFICATIONS_DOCTYPE_NAME,
    TAXATION_TYPE_DOCTYPE_NAME,
)

from ..utils.update_utils import update_documents


# def update_countries(response: dict | list, settings_name: str = None, **kwargs) -> None:
#     """Update ERPNext Countries from Crystal VSDC API response."""
#     if isinstance(response, str):
#         response = json.loads(response)

#     # Example Crystal response: [{"code": "UG", "name": "Uganda", "currency_code": "UGX"}]
#     field_mapping = {
#         "code": "code",
#         "code_name": "name",
#         "currency_code": "currency_code",
#         "code_description": "description",
#         "sort_order": "sort_order",
#     }

#     update_documents(response, COUNTRIES_DOCTYPE_NAME, field_mapping, settings_name=settings_name)


def update_currencies(response: dict | list, settings_name: str = None, **kwargs) -> None:
    """Update ERPNext Currencies from Crystal VSDC API response."""
    if isinstance(response, str):
        response = json.loads(response)

    # Example Crystal response: [{"iso_code": "UGX", "conversion_rate": 1.0, "active": true}]
    field_mapping = {
        "currency_name": "iso_code",
        "enabled": lambda x: 1 if x.get("active") else 0,
        "custom_conversion_rate": "conversion_rate",
    }

    update_documents(response, "Currency", field_mapping, filter_field="currency_name", settings_name=settings_name)


def update_packaging_units(response: dict | list, settings_name: str = None, **kwargs) -> None:
    """Update Packaging Units from Crystal VSDC API response."""
    if isinstance(response, str):
        response = json.loads(response)

    # Example Crystal response: [{"code": "BOX", "name": "Box", "description": "Standard Box"}]
    field_mapping = {
        "code": "code",
        "code_name": "name",
        "code_description": "description",
    }

    update_documents(response, PACKAGING_UNIT_DOCTYPE_NAME, field_mapping, settings_name=settings_name)


def update_unit_of_quantity(response: dict | list, settings_name: str = None, **kwargs) -> None:
    """Update Units of Quantity (UOM) from Crystal VSDC API response."""
    if isinstance(response, str):
        response = json.loads(response)

    # Example Crystal response: [{"code": "LTR", "name": "Liters", "description": "Liquid volume"}]
    field_mapping = {
        "code": "code",
        "code_name": "name",
        "code_description": "description",
    }

    update_documents(response, UNIT_OF_QUANTITY_DOCTYPE_NAME, field_mapping, settings_name=settings_name)


def update_taxation_type(response: dict | list, settings_name: str = None, **kwargs) -> None:
    """Update Taxation Types from Crystal VSDC API response."""
    if isinstance(response, str):
        response = json.loads(response)

    # Example Crystal response: [{"code": "VAT", "name": "Value Added Tax", "description": "Standard VAT"}]
    field_mapping = {
        "code": "code",
        "code_name": "name",
        "code_description": "description",
    }

    update_documents(response, TAXATION_TYPE_DOCTYPE_NAME, field_mapping, settings_name=settings_name)


def update_item_classification_codes(response: dict | list, **kwargs) -> None:
    """
    Update Item Classification Codes (HS/Tariff) from Crystal VSDC response.
    """
    field_mapping = {
        "classification_code": "itemClsCd",
        "classification_level": "itemClsLvl",
        "classification_name": "itemClsNm",
        "tax_type_code": "taxTyCd",
        "is_used": lambda x: 1 if str(x.get("useYn", "")).upper() == "Y" else 0,
        "is_frequently_used": lambda x: 1 if str(x.get("mjrTgYn", "")).upper() == "Y" else 0,
    }

    update_documents(
        response,
        ITEM_CLASSIFICATIONS_DOCTYPE_NAME,
        field_mapping,
        filter_field="classification_code",
    )
