// Copyright (c) 2025
// For license information, please see license.txt

const doctypeName = "Crystallised ZRA Smart Purchases";

frappe.ui.form.on(doctypeName, {
  refresh(frm) {
    let companyName = frappe.boot.sysdefaults.company;

    // Fallback if company not set
    if (!companyName) {
      frappe.call({
        method: "frappe.client.get_list",
        args: { doctype: "Company", fields: ["name"], limit_page_length: 1 },
        callback: function (res) {
          if (res.message?.length) {
            companyName = res.message[0].name;
          }
        },
      });
    }

    if (!frm.is_new()) {
      // -------------------------------------------------------------
      // 🔹 1. CREATE SUPPLIER
      // -------------------------------------------------------------
      frm.add_custom_button(
        __("Create Supplier"),
        () => {
          frappe.call({
            method:
              "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_supplier_from_smart_purchase",
            args: {
              request_data: {
                name: frm.doc.name,
                company_name: companyName,
                supplier_name: frm.doc.supplier_name,
                supplier_tpin: frm.doc.supplier_tpin,
                supplier_branch_id: frm.doc.supplier_branch_id,
                supplier_country: "Zambia",
                supplier_currency: "ZMW",
              },
            },
          });
        },
        __("Smart Actions")
      );

      // -------------------------------------------------------------
      // 🔹 2. CREATE ITEMS
      // -------------------------------------------------------------
      frm.add_custom_button(
        __("Create Items"),
        () => {
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

      // // -------------------------------------------------------------
      // // 🔹 3. CREATE PURCHASE INVOICE
      // // -------------------------------------------------------------
      // frm.add_custom_button(
      //   __("Create Purchase Invoice"),
      //   () => {
      //     frappe.call({
      //       method:
      //         "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_purchase_invoice_from_smart_request",
      //       args: {
      //         request_data: {
      //           company_name: frm.doc.company,
      //           purchase_id: frm.doc.purchase_id,
      //           supplier_name: frm.doc.supplier_name,
      //           supplier_tpin: frm.doc.supplier_tpin,
      //           branch: frm.doc.branch,
      //           organisation: frm.doc.organisation,
      //           invoice_no: frm.doc.invoice_number,
      //           invoice_date: frm.doc.sales_date,
      //           items: frm.doc.items,

      //           // ZRA field mapping
      //           rcptTyCd: frm.doc.rcptTyCd,
      //           pchsTyCd: frm.doc.pchsTyCd,
      //           regTyCd: frm.doc.regTyCd,
      //           pchsSttsCd: frm.doc.pchsSttsCd,

      //           custom_receipt_type: frm.doc.custom_receipt_type,
      //           custom_registration_type: frm.doc.custom_registration_type,
      //           custom_purchase_type: frm.doc.custom_purchase_type,
      //           custom_purchase_status: frm.doc.custom_purchase_status,
      //         },
      //       },
      //     });
      //   },
      //   __("Smart Actions")
      // );

      // -------------------------------------------------------------
      // 🔹 4. FETCH SMART PURCHASE DETAILS FROM ZRA
      // -------------------------------------------------------------
      frm.add_custom_button(
        __("Fetch Smart Purchase Details"),
        () => {
          frappe.call({
            method:
              "ca_erpnext_zra.ca_erpnext_zra.apis.smart_invoices.fetch_smart_purchase_details",
            args: { request_data: { id: frm.doc.name, company_name: companyName } },
          });
        },
        __("Smart Actions")
      );

      // -------------------------------------------------------------
      // 🔹 5. APPROVE / REJECT PURCHASE
      // -------------------------------------------------------------

      // Show buttons only in Pending or empty state
      if (!frm.doc.custom_purchase_status || frm.doc.custom_purchase_status === "Pending") {
        frm.add_custom_button(
          __("Approve Purchase"),
          () => {
            frappe.call({
              method:
                "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.approve_smart_purchase",
              args: { name: frm.doc.name },
              callback: () => frm.reload_doc(),
            });
          },
          __("Smart Workflow")
        );

        frm.add_custom_button(
          __("Reject Purchase"),
          () => {
            frappe.call({
              method:
                "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.reject_smart_purchase",
              args: { name: frm.doc.name },
              callback: () => frm.reload_doc(),
            });
          },
          __("Smart Workflow")
        );
      }
    }
  },
});
