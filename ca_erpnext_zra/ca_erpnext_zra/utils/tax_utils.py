# apps/ca_erpnext_zra/ca_erpnext_zra/ca_erpnext_zra/apis/tax_utils.py
import frappe
from frappe.model.document import Document
from frappe.utils import flt


def calculate_tax(doc: "Document") -> None:
	"""
	Crystal VSDC: Calculate and assign taxes for invoice items.

	- Prefer item-level tax templates.
	- Otherwise, use document-level taxes.
	- If neither exists, fallback to default Smart Invoice Settings.
	- Always recalc supply amount, VAT, totals (ZRA format).
	"""
	taxes = doc.get("taxes", [])
	has_item_level_tax = any(getattr(item, "item_tax_template", None) for item in doc.items)

	# Reset VAT amounts
	for item in doc.items:
		item.custom_vat_amount = 0

	if has_item_level_tax:
		_calculate_item_level_taxes(doc)
	elif taxes:
		_calculate_document_level_taxes(doc, taxes)
	else:
		_apply_default_tax_from_settings(doc)

	_set_taxation_type_codes(doc)
	# _recalculate_zra_amounts(doc)   # ensures amounts match ZRA rules


def _calculate_item_level_taxes(doc: "Document") -> None:
	for item in doc.items:
		if not item.item_tax_template:
			continue

		tax_template = frappe.get_doc("Item Tax Template", item.item_tax_template)
		for tax in tax_template.taxes:
			tax_rate = getattr(tax, "tax_rate", 0) or 0
			tax_amount = (item.base_net_amount * tax_rate) / 100
			item.custom_vat_amount = (item.custom_vat_amount or 0) + tax_amount
			item.custom_tax_rate = tax_rate


def _calculate_document_level_taxes(doc: "Document", taxes: list) -> None:
	for item in doc.items:
		for tax in taxes:
			tax_rate = tax.get("rate", 0)
			tax_amount = (item.base_net_amount * tax_rate) / 100
			item.custom_vat_amount = (item.custom_vat_amount or 0) + tax_amount
			item.custom_tax_rate = tax_rate


def _apply_default_tax_from_settings(doc: "Document") -> None:
	settings_name = frappe.get_value(
		"Crystal ZRA Smart Invoice Settings", {"company_name": doc.company}, "name"
	)
	if not settings_name:
		frappe.throw(f"No Crystal ZRA Smart Invoice Settings found for company {doc.company}")

	settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)
	if not settings.default_tax_rate:
		return

	for item in doc.items:
		tax_amount = (item.base_net_amount * settings.default_tax_rate) / 100
		item.custom_vat_amount = tax_amount
		item.custom_tax_rate = settings.default_tax_rate


def _set_taxation_type_codes(doc: "Document") -> None:
	for item in doc.items:
		rate = float(getattr(item, "custom_tax_rate", 0) or 0)
		if round(rate) == 16:
			item.custom_taxation_type = "A"
		elif round(rate) == 8:
			item.custom_taxation_type = "E"
		elif rate == 0:
			item.custom_taxation_type = "B"
		else:
			item.custom_taxation_type = "B"  # safe default


def _recalculate_zra_amounts(doc, method=None, *args, **kwargs) -> None:
	"""Final balancing step to avoid ZRA error 910."""
	total_taxable, total_vat, total_amount = 0, 0, 0

	for item in doc.items:
		supply = flt(item.base_net_amount, 2)
		vat = flt(item.custom_vat_amount, 2)
		line_total = flt(supply + vat, 2)

		# Map to ZRA expected fields
		item.sply_amt = supply
		item.vat_amt = vat
		item.tl_amt = supply  # ZRA expects tlAmt = supply (before VAT)
		item.tot_amt = line_total

		total_taxable += supply
		total_vat += vat
		total_amount += line_total

	doc.tot_taxbl_amt = flt(total_taxable, 2)
	doc.tot_tax_amt = flt(total_vat, 2)
	doc.tot_amt = flt(total_amount, 2)
