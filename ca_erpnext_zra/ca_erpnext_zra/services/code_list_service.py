import frappe
import json
from frappe.model.document import Document

from ..doctype.doctype_names_mapping import (
    
ITEM_CLASSIFICATIONS_DOCTYPE_NAME,
   
)

from ..utils.update_utils import update_documents

from ..apis.api_processor import process_request


CRYSTAL_CODES_DOCTYPE_NAME = "Crystal VSDC Codes"
CRYSTAL_CODES_CHILD_TABLE = "Crystal VSDC Codes Detail"


def sync_vsdc_codes(settings_name: str, LastReqDt: str = None, **kwargs) -> dict:
    """
    Fetch codes from Crystal VSDC and update them into custom DocTypes.
    """

    settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
    payload = {
        "tpin": settings.get_password("tpin"),
        "bhfId": "000",
        "lastReqDt": LastReqDt or "20231215000000"
    }

    response = process_request(
        request_data=payload,
        route_key="SelectCodes",
        request_method="POST",
        handler_function=handle_codes_response,
        settings_name=settings_name,
    )

    return response


def handle_codes_response(response: dict | str, settings_name: str = None, **kwargs) -> None:
    """Parse SelectCodes response from Crystal VSDC and update ERPNext DocTypes."""
    if isinstance(response, str):
        response = json.loads(response)

    if not response or "Result" not in response:
        frappe.throw("Invalid response from Crystal VSDC")

    cls_list = response["Result"]["data"].get("clsList", [])

    for cls in cls_list:
        # Parent mapping
        field_mapping = {
            "cdCls": "code_class",
            "cdClsNm": "code_class_name",
        }

        parent_doc = update_documents(
            [cls],
            CRYSTAL_CODES_DOCTYPE_NAME,
            field_mapping,
            unique_key="cdCls",
            return_docs=True,
        )[0]

        # Child mapping
        child_mapping = {
            "cd": "code",
            "cdNm": "code_name",
            "userDfnCd1": "user_def_cd1",
       
        }

        update_documents(
            cls.get("dtlList", []),
            CRYSTAL_CODES_CHILD_TABLE,
            child_mapping,
            unique_key="cd",
            parent=parent_doc.name,
            parenttype=CRYSTAL_CODES_DOCTYPE_NAME,
            parentfield="codes",
        )



def sync_item_codes(settings_name: str, LastReqDt: str = None, **kwargs) -> dict:
    """
    Fetch item codes from Crystal VSDC and update them into custom DocTypes.
    """
    settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
    payload = {
        "tpin": settings.get_password("tpin"),
        "bhfId": "000",
        "lastReqDt": LastReqDt or "20231215000000",
    }

    response = process_request(
        request_data=payload,
        route_key="selectItemsClass",  # <-- API route for item codes
        request_method="POST",
        handler_function=handle_item_codes_response,
        settings_name=settings_name,
    )

    return response


def handle_item_codes_response(response: dict | str, settings_name: str = None, **kwargs) -> None:
    """Parse Item Classification response from Crystal VSDC and update ERPNext DocType."""
    if isinstance(response, str):
        response = json.loads(response)

    if not response or "Result" not in response:
        frappe.throw("Invalid response from Crystal VSDC")

    item_cls_list = response["Result"]["data"].get("itemClsList", [])

    if not item_cls_list:
        return

    # Field mapping for classification codes
    field_mapping = {
        "itemClsCd": "item_cls_cd",
        "itemClsNm": "item_cls_nm",
        "itemClsLvl": "item_cls_lvl",
        "taxTyCd": "tax_ty_cd",
        "useYn": ("is_used", lambda v: 1 if str(v or "").upper() == "Y" else 0),
        "mjrTgYn": ("is_major_target", lambda v: 1 if str(v or "").upper() == "Y" else 0),
    }

    update_documents(
        item_cls_list,
      ITEM_CLASSIFICATIONS_DOCTYPE_NAME,
        field_mapping,
        unique_key="itemClsCd",  # unique key for classifications
    )