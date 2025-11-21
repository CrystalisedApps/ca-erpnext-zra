import csv

import frappe
import openpyxl


@frappe.whitelist()
def import_classification_codes(settings_name):
	"""
	Import Classification Codes into 'Crystal ZRA Smart Invoice Item Classification' DocType.

	Features:
	- Supports XLSX and CSV files.
	- Handles numeric and string codes.
	- Deduplicates against existing records and within the file.
	- Batched inserts with progress logging.
	- Automatically truncates Item Classification Name to 140 characters.
	- Ensures records are visible in Frappe UI.
	"""
	settings = frappe.get_doc("Crystal ZRA Smart Invoice Settings", settings_name)

	if not settings.classification_codes_file:
		frappe.throw("No file uploaded.")

	file_doc = frappe.get_doc("File", {"file_url": settings.classification_codes_file})
	file_path = file_doc.get_full_path()

	# -------------------------
	# Load file rows
	# -------------------------
	rows_to_insert = []

	# Get existing codes to skip duplicates
	existing_codes = set(
		frappe.db.get_all(
			"Crystal ZRA Smart Invoice Item Classification", fields=["item_cls_cd"], pluck="item_cls_cd"
		)
	)

	# -------------------------
	# XLSX
	# -------------------------
	if file_path.lower().endswith(".xlsx"):
		wb = openpyxl.load_workbook(file_path, read_only=True)
		sheet = wb.active
		headers = [cell.value for cell in sheet[1]]

		for row in sheet.iter_rows(min_row=2, values_only=True):
			row_data = dict(zip(headers, row))
			class_code = row_data.get("Class")
			class_title = row_data.get("Class Title")

			if class_code is not None:
				class_code = str(class_code).strip()
				class_title = str(class_title).strip()[:140] if class_title is not None else ""
				rows_to_insert.append({"item_cls_cd": class_code, "item_cls_nm": class_title})

	# -------------------------
	# CSV
	# -------------------------
	else:
		encodings = ["utf-8", "latin-1", "windows-1252"]
		file = None
		for enc in encodings:
			try:
				file = open(file_path, newline="", encoding=enc)
				break
			except UnicodeDecodeError:
				continue

		if not file:
			frappe.throw("Unable to read CSV file. Try saving as UTF-8.")

		with file:
			reader = csv.DictReader(file)
			for row in reader:
				class_code = row.get("class")
				class_title = row.get("class_title")

				if class_code is not None:
					class_code = str(class_code).strip()
					class_title = str(class_title).strip()[:140] if class_title is not None else ""
					rows_to_insert.append({"item_cls_cd": class_code, "item_cls_nm": class_title})

	# -------------------------
	# Deduplicate against DB and within file
	# -------------------------
	seen_codes = set(existing_codes)
	unique_rows = []
	for row in rows_to_insert:
		code = row["item_cls_cd"]
		if code not in seen_codes:
			unique_rows.append(row)
			seen_codes.add(code)

	# -------------------------
	# Insert in batches using ORM with progress logging
	# -------------------------
	BATCH_SIZE = 500
	batch = []
	inserted = 0

	for idx, row in enumerate(unique_rows, start=1):
		code = row["item_cls_cd"]

		# extra safety: check current batch for duplicates
		if code in [d.item_cls_cd for d in batch]:
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Crystal ZRA Smart Invoice Item Classification",
				"item_cls_cd": code,
				"item_cls_nm": row["item_cls_nm"],  # already truncated to 140 chars
			}
		)
		batch.append(doc)

		if len(batch) >= BATCH_SIZE:
			for d in batch:
				try:
					d.insert(ignore_permissions=True)
					inserted += 1
				except frappe.DuplicateEntryError:
					continue
			frappe.db.commit()
			batch = []
			frappe.publish_realtime("progress", {"message": f"Inserted {inserted} rows..."})
			frappe.logger().info(f"Inserted {inserted} rows so far.")

	# Insert remaining batch
	for d in batch:
		try:
			d.insert(ignore_permissions=True)
			inserted += 1
		except frappe.DuplicateEntryError:
			continue
	frappe.db.commit()

	frappe.publish_realtime("progress", {"message": f"Import complete. Total inserted: {inserted}"})
	frappe.logger().info(f"Import complete. Total inserted: {inserted}")

	return {
		"status": "success",
		"inserted": inserted,
		"file_type": "xlsx" if file_path.lower().endswith(".xlsx") else "csv",
	}
