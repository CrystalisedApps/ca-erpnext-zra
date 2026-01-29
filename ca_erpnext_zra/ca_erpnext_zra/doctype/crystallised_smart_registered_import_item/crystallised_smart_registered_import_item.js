// Copyright (c) 2025, Crystalised Apps and contributors
// For license information, please see license.txt

const doctypeName = "Crystallised Smart Registered Import Item";

frappe.ui.form.on(doctypeName, {
	refresh: function (frm) {
		let warehouse;

		frappe.db.get_value(
			"Crystal ZRA Smart Invoice Settings",
			{ name: frm.doc.settings },
			["default_import_warehouse"],
			(response) => {
				warehouse = response.default_import_warehouse;
			}
		);

		const item = [
			{
				item_classification_code: null,
				taxation_type_code: null,
				item_code: null,
				item_name: frm.doc.item_name,
				packaging_unit_code: frm.doc.packaging_unit_code,
				quantity_unit_code: frm.doc.quantity_unit_code,
				unit_price:
					parseFloat(frm.doc.invoice_foreign_currency_amount) /
					parseFloat(frm.doc.quantity).toFixed(2),
				quantity: frm.doc.quantity,
				imported_item: frm.doc.name,
				task_code: frm.doc.task_code,
				origin_nation_code: frm.doc.origin_nation_code,
				hs_code: frm.doc.hs_code,
				imported_item_status: frm.doc.imported_item_status,
				imported_item_status_code: frm.doc.imported_item_status_code,
			},
		];

		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Create Item"),
				function () {
					frappe.call({
						method: "ca_erpnext_zra.ca_erpnext_zra.apis.import_item.create_item_from_fetched_registered_import",
						args: {
							request_data: {
								items: item,
							},
						},
						callback: (response) => {
							frappe.msgprint(
								"Item has been created. Please go to the created Item and provide required Smart Item Details."
							);
						},
						error: (error) => {
							// Error Handling is Defered to the Server
						},
						freeze: true,
						freeze_message: __("Creating Item..."),
					});
				},
				__("Smart Actions")
			);

			frm.add_custom_button(
				__("Create Supplier"),
				function () {
					frappe.call({
						method: "ca_erpnext_zra.ca_erpnext_zra.utils.create_supplier.create_supplier_from_fetched_registered_import",
						args: {
							request_data: {
								name: frm.doc.name,
								supplier_name: frm.doc.suppliers_name || null,
								supplier_pin: frm.doc.suppliers_pin || null,
								supplier_currency: frm.doc.invoice_foreign_currency,
								supplier_nation: frm.doc.origin_nation_code,
							},
						},
						callback: (response) => {
							frappe.msgprint(
								__(
									"Supplier has been created. Please confirm the details captured."
								)
							);
						},
						error: (error) => {
							// Error Handling is Defered to the Server
						},
						freeze: true,
						freeze_message: __("Creating Supplier..."),
					});
				},
				__("Smart Actions")
			);

			frappe.db.get_value(
				"Item",
				{ item_code: frm.doc.item_name },
				["custom_item_registered", "name"],
				(response) => {
					if (parseInt(response.custom_item_registered) === 1) {
						if (
							frm.doc.imported_item_status == "Approved" ||
							frm.doc.imported_item_status == 3
						) {
							// frm.add_custom_button(
							// 	__("Create Purchase Invoice"),
							// 	function () {

							// 		frappe.call({
							// 			method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_invoice.create_purchase_invoice_from_request",
							// 			args: {
							// 				request_data: {
							// 					name: frm.doc.name,
							// 					supplier_invoice_no: null,
							// 					supplier_invoice_date: null,
							// 					supplier_name: frm.doc.suppliers_name,
							// 					supplier_currency:
							// 						frm.doc.invoice_foreign_currency,
							// 					supplier_nation: frm.doc.origin_nation_code,
							// 					supplier_branch_id: null,
							// 					exchange_rate:
							// 						frm.doc.foreign_currency_exchange_rate,
							// 					currency: frm.doc.invoice_foreign_currency,
							// 					amount: frm.doc.invoice_foreign_currency_amount,
							// 					items: item,
							// 					task_code: frm.doc.task_code,
							// 					company_name: company_name,
							// 				},
							// 			},
							// 			callback: (response) => {
							// 				frappe.msgprint("Purchase Invoice has been created.");
							// 			},
							// 			error: (error) => {
							// 				// Error Handling is Defered to the Server
							// 			},
							// 			freeze: true,
							// 			freeze_message: __("Creating Purchase Invoice..."),
							// 		});
							// 	},
							// 	__("Smart Actions")
							// );
							frm.add_custom_button(
								__("Create Purchase Invoice"),
								function () {
									const dialog = new frappe.ui.Dialog({
										title: __("Purchase Invoice Settings"),
										fields: [
											{
												fieldname: "creditors_account",
												label: __("Creditors Account"),
												fieldtype: "Link",
												options: "Account",
												reqd: 1,
												filters: {
													account_type: "Payable",
													company: frm.doc.company,
													account_currency:
														frm.doc.invoice_foreign_currency,
												},
											},
											{
												fieldname: "default_warehouse",
												label: __("Default Warehouse"),
												fieldtype: "Link",
												options: "Warehouse",
												reqd: 1,
												default: warehouse,
												filters: {
													company: frm.doc.company,
												},
											},
										],
										primary_action_label: __("Create"),
										primary_action(values) {
											dialog.hide();

											frappe.call({
												method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_invoice.create_purchase_invoice_from_request",
												args: {
													request_data: {
														name: frm.doc.name,
														supplier_invoice_no: null,
														supplier_invoice_date: null,
														supplier_name: frm.doc.suppliers_name || null,
														supplier_pin:frm.doc.suppliers_pin || null,
														supplier_currency:
															frm.doc.invoice_foreign_currency,
														supplier_nation:
															frm.doc.origin_nation_code,
														supplier_branch_id: null,
														exchange_rate:
															frm.doc.foreign_currency_exchange_rate,
														currency: frm.doc.invoice_foreign_currency,
														amount: frm.doc
															.invoice_foreign_currency_amount,
														items: item,
														task_code: frm.doc.task_code,
														company_name: frm.doc.company,
														creditors_account:
															values.creditors_account,
														default_warehouse:
															values.default_warehouse,
														branch_code: frm.doc.branch_code,
													},
												},
												callback: (response) => {
													frappe.msgprint(
														__("Purchase Invoice has been created.")
													);
												},
												error: (error) => {
													frappe.msgprint({
														title: __("Error"),
														indicator: "red",
														message: __(
															"Failed to create Purchase Invoice."
														),
													});
												},
												freeze: true,
												freeze_message: __("Creating Purchase Invoice..."),
											});
										},
									});

									dialog.show();
								},
								__("Smart Actions")
							);
						}

						if (frm.doc.imported_item_status !== "Approved") {
							frm.add_custom_button(
								"Update Import Item",
								function () {
									// Create dialog with two options
									const dialog = new frappe.ui.Dialog({
										title: __("Select Import Item Status"),
										fields: [
											{
												fieldname: "imported_item_status_code",
												label: __("Import Item Status Code"),
												fieldtype: "Select",
												options: [
													{ value: "Approved", label: __("Approved") },
													{ value: "Cancelled", label: __("Cancelled") },
												],
												default:
													frm.doc.imported_item_status_code ||
													"Approved",
												reqd: 1,
											},
										],
										primary_action_label: __("Update"),
										primary_action: function (values) {
											dialog.hide();

											frappe.call({
												method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_invoice.update_registered_import_item",
												args: {
													request_data: {
														name: frm.doc.name,
														settings_name: frm.doc.settings,
														item_name: frm.doc.item_name,
														task_code: frm.doc.task_code,
														branch_code: frm.doc.branch_code,
														declaration_date: frm.doc.declaration_date,
														item_sequence: frm.doc.item_sequence,
														hs_code: frm.doc.hs_code,
														imported_item_status_code:
															values.imported_item_status_code,

														modified_by: frm.doc.modified_by,
														document_name: frm.doc.name,
													},
												},
												callback: (response) => {
													frappe.msgprint(
														"Update of Import Item(s) has been queued."
													);
												},
												error: (error) => {
													// Error Handling is Deferred to the Server
												},
												freeze: true,
												freeze_message: __("Updating Import Item..."),
											});
										},
									});

									dialog.show();
								},
								__("Smart Actions")
							);
						}
					} else {
						frm.set_intro(
							__(
								"Item not registered yet. Please register it to allow Update of Import Item."
							),
							"red"
						);
					}
				}
			);
		}
	},
});
