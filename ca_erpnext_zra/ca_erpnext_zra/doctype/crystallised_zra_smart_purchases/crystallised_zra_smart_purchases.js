// Copyright (c) 2025
// For license information, please see license.txt

const doctypeName = "Crystallised ZRA Smart Purchases";

frappe.ui.form.on(doctypeName, {
  refresh: function (frm) {
    let companyName = frappe.boot.sysdefaults.company;

    // Fallback to fetch company if not in sysdefaults
    if (!companyName) {
      frappe.call({
        method: "frappe.client.get_list",
        args: {
          doctype: "Company",
          fields: ["name"],
          limit_page_length: 1,
        },
        callback: function (response) {
          if (response.message && response.message.length > 0) {
            companyName = response.message[0].name;
          }
        },
      });
    }

    if (!frm.is_new()) {
      // 🔹 Create Supplier from Smart data
      frm.add_custom_button(
        __("Create Supplier"),
        function () {
          frappe.call({
            method:
              "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_supplier_from_smart_purchase",
            args: {
              request_data: {
                name: frm.doc.name,
                company_name: companyName,
                supplier_name: frm.doc.supplier_name,
                supplier_tpin: frm.doc.supplier_tpin,
                  supplier_name: frm.doc.supplier_name,
      
                    supplier_branch_id: frm.doc.supplier_branch_id,
                    supplier_country: "Zambia",
                    supplier_currency: "ZMW",
              },
            },
          });
        },
        __("Smart Actions")
      );

      // 🔹 Create Items from Smart purchase
      frm.add_custom_button(
        __("Create Items"),
        function () {
          frappe.call({
            method:
              "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_items_from_smart_purchase",
            args: {
              request_data: {
                name: frm.doc.name,
                company_name: companyName,
                items: frm.doc.items,
              },
            },
          });
        },
        __("Smart Actions")
      );

      // 🔹 Create Purchase Invoice in ERPNext
      frm.add_custom_button(
        __("Create Purchase Invoice"),
        function () {
          frappe.call({
            method:
              "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_purchase_invoice_from_smart_request",
            args: {
              request_data: {
          
      company_name: frm.doc.company,
      purchase_id: frm.doc.purchase_id,
      supplier_name: frm.doc.supplier_name,
      supplier_tpin: frm.doc.supplier_tpin,
      branch: frm.doc.branch,
      organisation: frm.doc.organisation,
      invoice_no: frm.doc.invoice_number,
      invoice_date: frm.doc.sales_date,
      items: frm.doc.items,
              },
            },
          });
        },
        __("Smart Actions")
      );

      // 🔹 Fetch Smart Purchase Details from ZRA API
      frm.add_custom_button(
        __("Fetch Smart Purchase Details"),
        function () {
          frappe.call({
            method:
              "ca_erpnext_zra.ca_erpnext_zra.apis.smart_invoices.fetch_smart_purchase_details",
            args: {
              request_data: {
                id: frm.doc.name,
                company_name: companyName,
              },
            },
          });
        },
        __("Smart Actions")
      );
    }
  },
});
