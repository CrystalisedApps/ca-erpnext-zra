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

from ..apis.api_processor import process_request


CRYSTAL_CODES_DOCTYPE_NAME = "Crystal VSDC Codes"
CRYSTAL_CODES_CHILD_TABLE = "Code Details"

def sync_vsdc_codes(settings_name: str, last_req_dt: str = None, **kwargs) -> dict:
    """
    Fetch codes from Crystal VSDC and update them into custom DocTypes.
    """

    settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
    payload = {
        "tpin": settings.tpin,
        "bhfId": "000",
        "lastReqDt": last_req_dt or None,
    }

    response = process_request(
        request_data=payload,
        route_key="SelectCodes",
        request_method="POST",
        settings_name=settings_name,
    )

    if isinstance(response, str):
        response = json.loads(response)

    if not response or "Result" not in response:
        frappe.throw("Invalid response from Crystal VSDC")

    cls_list = response["Result"]["data"].get("clsList", [])

    for cls in cls_list:
        field_mapping = {
            "cdCls": "code_class",
            "cdClsNm": "code_class_name",
        }

        # Save/update the parent "Crystal VSDC Codes" record
        parent_doc = update_documents(
            [cls],
            CRYSTAL_CODES_DOCTYPE_NAME,
            field_mapping,
            settings_name=settings_name,
            return_docs=True,  # so we can attach children
        )[0]

        # Now handle children (dtlList → Code Details)
        child_mapping = {
            "cd": "code",
            "cdNm": "code_name",
            "userDfnCd1": "user_def_cd1",
            "userDfnCd2": "user_def_cd2",
        }

        update_documents(
            cls.get("dtlList", []),
            CRYSTAL_CODES_CHILD_TABLE,
            child_mapping,
            parent=parent_doc.name,
            parenttype=CRYSTAL_CODES_DOCTYPE_NAME,
            parentfield="codes",
            settings_name=settings_name,
        )

    return response


# def update_item_classification_codes(response: dict | list, **kwargs) -> None:
#     """
#     Update Item Classification Codes (HS/Tariff) from Crystal VSDC response.
#     """
#     field_mapping = {
#         "classification_code": "itemClsCd",
#         "classification_level": "itemClsLvl",
#         "classification_name": "itemClsNm",
#         "tax_type_code": "taxTyCd",
#         "is_used": lambda x: 1 if str(x.get("useYn", "")).upper() == "Y" else 0,
#         "is_frequently_used": lambda x: 1 if str(x.get("mjrTgYn", "")).upper() == "Y" else 0,
#     }

#     update_documents(
#         response,
#         ITEM_CLASSIFICATIONS_DOCTYPE_NAME,
#         field_mapping,
#         filter_field="classification_code",
#     )
