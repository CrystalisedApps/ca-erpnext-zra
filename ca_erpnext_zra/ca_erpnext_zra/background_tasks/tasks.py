import frappe
from ..apis.api_processor import process_request
# from ..apis.api_builder import EndpointsBuilder
# from ..utils import settings_utils
from ..services.code_list_service import (update_currencies,
                                          update_packaging_units,
                                          sync_vsdc_codes,
                                          update_taxation_type,
                                          update_item_classification_codes,
                                          update_unit_of_quantity)

import json
import frappe
from ..apis.api_processor import process_request
from ..services.code_list_service import update_documents

CRYSTAL_CODES_DOCTYPE_NAME = "Crystal VSDC Codes"
CRYSTAL_CODES_CHILD_TABLE = "Crystal VSDC Codes Detail"


@frappe.whitelist()
def refresh_vsdc_codes(settings_name: str, last_req_dt: str = None) -> dict:
    """
    Fetch and update all code lists (currencies, packaging units, taxation, etc.)
    from Crystal VSDC using the SelectCodes endpoint.
    """
    return sync_vsdc_codes(settings_name=settings_name, last_req_dt=last_req_dt)


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



@frappe.whitelist()
def get_item_classification_codes(settings_name: str, request_data: dict) -> str:
    """Fetch item classification codes (HS/Tariff) from ZRA VSDC."""
    return process_request(
        request_data,
        "ItemClsSearchReq",
        update_item_classification_codes,
        settings_name=settings_name,
    )
