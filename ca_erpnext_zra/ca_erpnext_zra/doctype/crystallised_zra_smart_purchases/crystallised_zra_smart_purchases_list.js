// Copyright (c) 2025, Crystalised Apps and contributors
// For license information, please see license.txt

const doctypeName = "Crystallised ZRA Smart Purchases";

frappe.listview_settings[doctypeName] = {
  onload: function (listview) {
    const companyName = frappe.boot.sysdefaults.company;

    listview.page.add_inner_button(__("Get Raised Purchases"), function () {
      frappe.confirm(
        `Fetch raised purchases from ZRA Smart Invoice System for <b>${companyName}</b>?`,
        () => {
          frappe.call({
            method:
              "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.perform_purchases_search",
            args: {
              company: companyName, // Pass company directly (not inside request_data)
            },
            freeze: true,
            freeze_message: __("Fetching Purchases from ZRA Smart Invoice System..."),
            callback: function (response) {
              if (!response.exc) {
                frappe.show_alert({
                  message: __("Smart purchases fetch initiated successfully"),
                  indicator: "green",
                });
              }
            },
            error: function (error) {
              frappe.msgprint({
                title: __("Error"),
                message: __("Failed to contact ZRA Smart API. Check logs for details."),
                indicator: "red",
              });
            },
          });
        }
      );
    });
  },
};
