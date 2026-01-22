# Copyright (c) 2025, Crystalised Apps
# For license information, please see license.txt

from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe.query_builder import DocType
from pypika.functions import Avg, Min, Max


def execute(
    filters: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], None, Dict[str, Any]]:
    return t(filters).run()


class t:
    """Document Submission Time Analysis"""
    
    def __init__(self, filters: Optional[Dict[str, Any]] = None) -> None:
        self.filters = frappe._dict(filters or {})

        self.columns = [
            {"fieldname": "doctype", "label": "Document Type", "fieldtype": "Data", "width": 200},
            {"fieldname": "avg_time", "label": "Average Time (s)", "fieldtype": "Float", "width": 200},
            {"fieldname": "min_time", "label": "Min Time (s)", "fieldtype": "Float", "width": 200},
            {"fieldname": "max_time", "label": "Max Time (s)", "fieldtype": "Float", "width": 200},
        ]

        self.data: List[Dict[str, Any]] = []
        self.chart: Dict[str, Any] = {}

        # Only ZRA-relevant DocTypes
        self.tracked_docs = {
            "Invoice": DocType("Sales Invoice"),
            "Credit Note": DocType("Sales Invoice"),
            "Purchase Invoice": DocType("Purchase Invoice"),
        }

    def run(self):
        self.fetch_data()
        self.prepare_chart()
        return self.columns, self.data, None, self.chart

    # -----------------------------------------------------
    # Fetch submission times
    # -----------------------------------------------------
    def fetch_data(self) -> None:
        from_date = self.filters.get("from_date")
        to_date = self.filters.get("to_date")

        for label, doctype in self.tracked_docs.items():
            meta = frappe.get_meta("Sales Invoice" if label in ["Invoice", "Credit Note"] else label)

            has_sent = meta.has_field("custom_sent_to_zra")
            has_status = meta.has_field("custom_zra_status")

            if not (has_sent and has_status):
                continue  # Skip DocTypes without ZRA integration

            # Only include successfully accepted documents
            completion_condition = (doctype.custom_sent_to_zra == 1) & (doctype.custom_zra_status == "ACCEPTED")

            # Submission time in seconds
            submission_time = doctype.modified - doctype.creation

            query = (
                frappe.qb.from_(doctype)
                .select(
                    Avg(submission_time).as_("avg_time"),
                    Min(submission_time).as_("min_time"),
                    Max(submission_time).as_("max_time"),
                )
                .where(completion_condition)
                .where(submission_time <= 300)  # Cap outliers at 5 min
            )

            if from_date:
                query = query.where(doctype.creation >= from_date)
            if to_date:
                query = query.where(doctype.creation <= to_date)

            # Invoice vs Credit Note separation
            if label == "Invoice":
                query = query.where(doctype.is_return == 0)
            elif label == "Credit Note":
                query = query.where(doctype.is_return == 1)

            try:
                row = query.run(as_dict=True)[0]
                row["doctype"] = label
                self.data.append(row)
            except Exception as e:
                frappe.log_error(title="Document Submission Time Analysis Error", message=f"{label}: {str(e)}")

    # -----------------------------------------------------
    # Chart
    # -----------------------------------------------------
    def prepare_chart(self) -> None:
        self.chart = {
            "data": {
                "labels": [row["doctype"] for row in self.data],  # X-axis = DocType
                "datasets": [
                    {"name": "Average Time", "values": [row["avg_time"] for row in self.data]},
                    {"name": "Min Time", "values": [row["min_time"] for row in self.data]},
                    {"name": "Max Time", "values": [row["max_time"] for row in self.data]},
                ],
            },
            "type": "bar",
            "axis_options": {"xIsSeries": True},
        }
