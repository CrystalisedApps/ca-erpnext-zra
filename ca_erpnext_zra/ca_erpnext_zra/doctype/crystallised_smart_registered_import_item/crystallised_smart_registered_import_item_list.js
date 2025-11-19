// Copyright (c) 2025, Crystalised Apps and contributors
// For license information, please see license.txt

const doctypeName = "Crystallised Smart Registered Import Item";

frappe.listview_settings[doctypeName] = {
	onload: function (listview) {
		const company = frappe.boot.sysdefaults.company;

		listview.page.add_inner_button(__("Get Import Items"), function () {
			frappe.call({
				method: "ca_erpnext_zra.ca_erpnext_zra.apis.import_item.select_import_items_all_branches",
				args: { company_name: company },
				callback: function (r) {},
				error: function (err) {},
			});
		});
	},
};
