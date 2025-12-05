frappe.listview_settings["Crystallised ZRA Smart Purchases"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Get Raised Purchases"), function () {

			// Fetch companies
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Company",
					fields: ["name"],
					limit_page_length: 999,
				},
				callback(companyRes) {
					let companies = companyRes.message || [];

					let dialog = new frappe.ui.Dialog({
						title: "Fetch Purchases from ZRA",
						fields: [
							{
								fieldname: "company",
								label: "Company",
								fieldtype: "Select",
								reqd: 1,
								options: companies.map(c => c.name).join("\n"),
								change() {
									let company = dialog.get_value("company");

									// Fetch branches server-side (safe)
									frappe.call({
										method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.get_branches_for_company",
										args: { company },
										callback(res) {
											const branches = res.message || [];
											dialog.set_df_property(
												"branch",
												"options",
												branches.map(b => b.name).join("\n")
											);
										},
									});
								}
							},
							{
								fieldname: "branch",
								label: "Branch",
								fieldtype: "Select",
								reqd: 1,
								options: "",
								description: "Select company first",
							},
						],
						primary_action_label: "Fetch Purchases",
						primary_action(values) {
							dialog.hide();

							frappe.call({
								method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.perform_purchases_search",
								args: {
									company: values.company,
									branch: values.branch,
								},
								freeze: true,
								freeze_message: __("Fetching Purchases..."),
								callback() {
									frappe.show_alert({
										message: __("Purchases Fetch Initiated"),
										indicator: "green",
									});
								}
							});
						},
					});

					dialog.show();
				}
			});
		});
	},
};
