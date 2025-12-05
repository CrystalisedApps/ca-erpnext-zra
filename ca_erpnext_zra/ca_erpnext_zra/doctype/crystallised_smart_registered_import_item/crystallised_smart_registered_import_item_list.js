// Copyright (c) 2025, Crystalised Apps and contributors
// For license information, please see license.txt

const doctypeName = "Crystallised Smart Registered Import Item";

frappe.listview_settings[doctypeName] = {
	onload: function (listview) {
		const default_company = frappe.boot.sysdefaults.company;

		listview.page.add_inner_button(__("Get Import Items"), function () {
			const dialog = new frappe.ui.Dialog({
				title: __("Select Company"),
				fields: [
					{
						fieldname: "company",
						label: __("Company"),
						fieldtype: "Link",
						options: "Company",
						reqd: 1,
						default: default_company,
					},
				],
				primary_action_label: __("Fetch"),
				primary_action(values) {
					dialog.hide();

					frappe.call({
						method: "ca_erpnext_zra.ca_erpnext_zra.apis.import_item.select_import_items_all_branches",
						args: {
							company_name: values.company,
						},
						callback: function (r) {},
						error: function (err) {
							frappe.msgprint({
								title: __("Error"),
								indicator: "red",
								message: __("Failed to fetch Import Items."),
							});
						},
						freeze: true,
						freeze_message: __("Fetching Import Items..."),
					});
				},
			});

			dialog.show();
		});
	},
};
