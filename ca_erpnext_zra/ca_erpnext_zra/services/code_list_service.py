import json

import frappe
from frappe.model.document import Document

from ..apis.api_processor import process_request
from ..doctype.doctype_names_mapping import (
	ITEM_CLASSIFICATIONS_DOCTYPE_NAME,
)
from ..utils.update_utils import update_documents

CRYSTAL_CODES_DOCTYPE_NAME = "Crystal VSDC Codes"
CRYSTAL_CODES_CHILD_TABLE = "Crystal VSDC Codes Detail"


def sync_vsdc_codes(settings_name: str, LastReqDt: str = None, **kwargs) -> dict:
	"""
	Fetch codes from Crystal VSDC and update them into custom DocTypes.
	"""

	settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
	payload = {"tpin": settings.tpin, "bhfId": "000", "lastReqDt": LastReqDt or "20231215000000"}

	response = process_request(
		request_data=payload,
		route_key="SelectCodes",
		request_method="POST",
		handler_function=handle_codes_response,
		settings_name=settings_name,
	)

	return response


def handle_codes_response(response: dict | str, settings_name: str | Name = None, **kwargs) -> None:
	"""Parse SelectCodes response from Crystal VSDC and update ERPNext DocTypes."""
	if isinstance(response, str):
		response = json.loads(response)

	if not response or "Result" not in response:
		frappe.throw("Invalid response from Crystal VSDC")

	cls_list = response["Result"]["data"].get("clsList", [])

	# Mapping Crystal code classes -> ERPNext Doctypes + field mapping
	doctype_map = {
		"04": {  # Taxation Types
			"doctype": "Crystallised ZRA Smart Taxation Type",
			"field_mapping": {"cd": "code", "cdNm": "code_name", "userDfnCd1": "user_defined_code_1"},
			"unique_key": "c",
			"parent_fields": {
				"cdCls": "class_code",
			},
		},
		"05": {
			"doctype": "Crystallised Smart Country",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {
				"cdCls": "class_code",
			},
		},
		"06": {
			"doctype": "Crystallised Smart Sale Category",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"07": {
			"doctype": "Crystallised Smart Payment Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"09": {
			"doctype": "Crystallised Smart Branch Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"10": {
			"doctype": "Crystallised Smart Unit Of Quantity",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
		},
		"11": {
			"doctype": "Crystallised Smart Sale Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"12": {
			"doctype": "Crystallised Smart Stock IO Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"13": {
			"doctype": "Crystallised Smart Default Information",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"14": {
			"doctype": "Crystallised Smart Transaction Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"17": {  # Packaging Units
			"doctype": "Crystallised Smart Packaging Unit",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"20": {
			"doctype": "Crystallised Smart Customer Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"21": {
			"doctype": "Crystallised Smart Detail Information Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"22": {
			"doctype": "Crystallised Smart Travel Purpose",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"23": {
			"doctype": "Crystallised Smart Commercial Invoice Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"24": {
			"doctype": "Crystallised Smart Item Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"26": {
			"doctype": "Crystallised Smart Import Item Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"27": {
			"doctype": "Crystallised Smart Departure Incoterm",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"28": {
			"doctype": "Crystallised Smart Destination Incoterm",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"29": {
			"doctype": "Crystallised Smart Export Charges",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"30": {
			"doctype": "Crystallised Smart Zambia Ports",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"32": {
			"doctype": "Crystallised Smart Credit Note Reason",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"33": {  # Currency Codes
			"doctype": "Crystallised Smart Currency",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
				"userDfnCd1": "user_defined_code_1",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"34": {
			"doctype": "Crystallised Smart Purchase Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"35": {
			"doctype": "Crystallised Smart Reason of Inventory Adjustment",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"36": {
			"doctype": "Crystallised Smart Bank",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"37": {
			"doctype": "Crystallised Smart Sales Receipt Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"38": {
			"doctype": "Crystallised Smart Purchase Receipt Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"42": {
			"doctype": "Crystallised Smart Invoice Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"44": {
			"doctype": "Crystallised Smart Provisional Invoice Finalization Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"56": {
			"doctype": "Crystallised Smart Value Credit Note Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"48": {
			"doctype": "Crystallised Smart Locale",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"49": {
			"doctype": "Crystallised Smart Provisional Category Level",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"55": {
			"doctype": "Crystallised Smart VAT Type",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"58": {
			"doctype": "Crystallised Smart Reason For Value Credit Note",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"60": {
			"doctype": "Crystallised Smart Excise Duties",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"61": {
			"doctype": "Crystallised Smart Insurance Premium Levy",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"62": {
			"doctype": "Crystallised Smart Tourism Levy",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"64": {
			"doctype": "Crystallised Smart Excise Tax Registration Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {
				"cdCls": "class_code",
			},
		},
		"65": {
			"doctype": "Crystallised Smart IPL Registration Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"66": {
			"doctype": "Crystallised Smart Tourism Levy Registration Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"67": {
			"doctype": "Crystallised Smart Reason For Debit Note",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {"cdCls": "class_code", "userDfnCd1": "user_defined_name_1"},
		},
		"68": {
			"doctype": "Crystallised Smart Rental Income Status",
			"field_mapping": {
				"cd": "code",
				"cdNm": "code_name",
			},
			"unique_key": "code",
			"parent_fields": {
				"cdCls": "class_code",
			},
		},
	}

	for cls in cls_list:
		cd_cls = cls.get("cdCls")
		if cd_cls not in doctype_map:
			frappe.log_error(f"Unknown code class received: {cd_cls}", "VSDC Sync - Unmapped Code Class")
			continue

		config = doctype_map[cd_cls]
		doctype = config["doctype"]
		field_mapping = config["field_mapping"]
		unique_key = config["unique_key"]
		# parent_fields = config.get("parent_fields", {})

		# Save parent info (ensures class metadata is captured)
		# parent_doc = update_documents(
		#     [cls],  # use class-level dict
		#     doctype,
		#     parent_fields,
		#     unique_key="cdCls",   # use class code as unique identifier
		#     return_docs=True
		# )[0]

		# Save child list into same doctype
		update_documents(
			cls.get("dtlList", []), doctype, field_mapping, unique_key=unique_key, ignore_if_duplicate=True
		)


def sync_item_codes(settings_name: str, LastReqDt: str | None = None, **kwargs) -> dict:
	"""
	Fetch item codes from Crystal VSDC and update them into custom DocTypes.
	"""
	settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
	payload = {
		"tpin": settings.tpin,
		"bhfId": "000",
		"lastReqDt": LastReqDt or "20231215000000",
	}

	response = process_request(
		request_data=payload,
		route_key="selectItemsClass",
		request_method="POST",
		handler_function=handle_item_codes_response,
		settings_name=settings_name,
	)

	return response


def handle_item_codes_response(response: dict | str, settings_name: str | None = None, **kwargs) -> None:
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
