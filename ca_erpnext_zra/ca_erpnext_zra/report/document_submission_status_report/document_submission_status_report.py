# Copyright (c) 2025, Crystalised Apps
# For license information, please see license.txt

from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe.query_builder import DocType
from pypika.functions import Sum
from pypika.terms import Case


def execute(
    filters: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], None, Dict[str, Any]]:
    return DocumentSubmissionStatusAnalytics(filters).run()


class DocumentSubmissionStatusAnalytics:
    def __init__(self, filters: Optional[Dict[str, Any]] = None) -> None:
        self.filters = frappe._dict(filters or {})

        self.columns = [
            {"fieldname": "doctype", "label": "Document Type", "fieldtype": "Data", "width": 300},
            # {"fieldname": "sent", "label": "Sent", "fieldtype": "Int", "width": 120},
            {"fieldname": "not_sent", "label": "Not Sent", "fieldtype": "Int", "width": 120},
            {"fieldname": "failed", "label": "Failed", "fieldtype": "Int", "width": 120},
            {"fieldname": "successful", "label": "Successful", "fieldtype": "Int", "width": 120},
            {"fieldname": "total", "label": "Total", "fieldtype": "Int", "width": 120},
        ]

        self.data: List[Dict[str, Any]] = []
        self.chart: Dict[str, Any] = {}

        self.tracked_docs = {
            "Item": DocType("Item"),
            "Invoice": DocType("Sales Invoice"),
            "Credit Note": DocType("Sales Invoice"),
            "Purchase Invoice": DocType("Purchase Invoice"),
            "Stock Ledger Entry": DocType("Stock Ledger Entry"),
        }

    def run(self):
        self.fetch_data()
        self.prepare_chart()
        return self.columns, self.data, None, self.chart

    # -----------------------------------------------------
    # Core data aggregation
    # -----------------------------------------------------

    def fetch_data(self) -> None:
        from_date = self.filters.get("from_date")
        to_date = self.filters.get("to_date")

        for label, doctype in self.tracked_docs.items():
            meta = frappe.get_meta(
                "Sales Invoice" if label in ["Invoice", "Credit Note"] else label
            )

            # Detect available fields safely
         
            has_success_1 = meta.has_field("custom_successfully_submitted")
            has_success_2 = meta.has_field("custom_submitted_successfully")

            # SENT condition (submission attempted)
          

            # SUCCESS condition (any success flag true)
            success_conditions = []

            if has_success_1:
                success_conditions.append(doctype.custom_successfully_submitted)

            if has_success_2:
                success_conditions.append(doctype.custom_submitted_successfully)

            success_condition = None
            if success_conditions:
                success_condition = success_conditions[0]
                for cond in success_conditions[1:]:
                    success_condition |= cond

        

          
            # Build query
            query = frappe.qb.from_(doctype).select(
              

                Sum(Case().when(success_condition, 1).else_(0)).as_("successful")
                if success_condition else Sum(0).as_("successful"),

               
                Sum(1).as_("total"),
            )

            # Date filters
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
                frappe.log_error(
                    title="Submission Status Report Error",
                    message=f"{label}: {str(e)}"
                )

    # -----------------------------------------------------
    # Chart
    # -----------------------------------------------------

    def prepare_chart(self) -> None:
        self.chart = {
            "data": {
                "labels": [row["doctype"] for row in self.data],
                "datasets": [
                    # {"name": "Sent", "values": [row["sent"] for row in self.data]},
                    # {"name": "Not Sent", "values": [row["not_sent"] for row in self.data]},
                    # {"name": "Failed", "values": [row["failed"] for row in self.data]},
                    {"name": "Successful", "values": [row["successful"] for row in self.data]},
                ],
            },
            "type": "bar",
            "axis_options": {"xIsSeries": True},
        }
