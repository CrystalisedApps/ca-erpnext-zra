from datetime import datetime

import frappe
from frappe.query_builder import DocType

from ..doctype.doctype_names_mapping import (
	ROUTES_TABLE_CHILD_DOCTYPE_NAME,
	ROUTES_TABLE_DOCTYPE_NAME,
)


def get_route_path(
	search_field: str,
	vendor: str = "Crystal VSDC",
	routes_table_doctype: str = ROUTES_TABLE_CHILD_DOCTYPE_NAME,
	parent_doctype: str = ROUTES_TABLE_DOCTYPE_NAME,
) -> tuple[str, str] | None:
	"""
	Fetch the API route path for CrystalSmart Invoice based on the search field.

	Args:
	    search_field (str): Function name or identifier used to match the route.
	    vendor (str, optional): Defaults to 'ZRA VSDC'.
	    routes_table_doctype (str, optional): Child table containing route details.
	    parent_doctype (str, optional): Parent doctype holding vendor routes.

	Returns:
	    tuple[str, str] | None: (url_path, last_request_date) if found, otherwise (None, None).
	"""
	RoutesTable = DocType(routes_table_doctype)
	ParentTable = DocType(parent_doctype)

	query = (
		frappe.qb.from_(RoutesTable)
		.join(ParentTable)
		.on(RoutesTable.parent == ParentTable.name)
		.select(RoutesTable.url_path, RoutesTable.last_request_date)
		.where((RoutesTable.url_path_function.like(search_field)) & (ParentTable.vendor.like(vendor)))
		.limit(1)
	)

	results = query.run(as_dict=True)

	if results:
		return (results[0]["url_path"], results[0]["last_request_date"])

	return None, None


def build_datetime_from_string(date_string: str, format: str = "%Y-%m-%d %H:%M:%S") -> datetime:
	"""Builds a Datetime object from string, and format provided

	Args:
	    date_string (str): The string to build object from
	    format (str, optional): The format of the date_string string. Defaults to "%Y-%m-%d".

	Returns:
	    datetime: The datetime object
	"""
	date_object = datetime.strptime(date_string, format)

	return date_object

def update_last_request_date(
	response_datetime: str,
	route: str,
	routes_table: str = ROUTES_TABLE_CHILD_DOCTYPE_NAME,
) -> None:

	doc = frappe.get_doc(
		routes_table,
		{"url_path": route},
		["*"],
	)

	# Handle datetime or string input
	if isinstance(response_datetime, datetime):
		doc.last_request_date = response_datetime
	else:
		doc.last_request_date = build_datetime_from_string(
			response_datetime,
			"%Y%m%d%H%M%S"
		)

	doc.save()
	frappe.db.commit()

