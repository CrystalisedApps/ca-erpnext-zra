// === Doctype definitions ===
const parentDoctype = "Sales Invoice";
const childDoctype = `${parentDoctype} Item`;

// Crystal VSDC-specific doctypes
const packagingUnitDoctypeName = "Crystallised Smart Packing Unit";
const unitOfQuantityDoctypeName = "Crystallised Smart Quantity Unit";
const taxationTypeDoctypeName = "Crystallised ZRA Smart Taxation Type";
const settingsDoctypeName = "Crystal ZRA Smart Invoice Settings";

// === Real-time form refresh handler ===
frappe.realtime.on("refresh_form", function (name) {
	const currentForm = cur_frm;
	if (currentForm && currentForm.doc.name === name) {
		currentForm.reload_doc();
	}
});

// === Parent Doctype: Sales Invoice ===
frappe.ui.form.on(parentDoctype, {
	refresh: async function (frm) {
		await updateTaxAmountLabel(frm);

		// Fetch active VSDC settings for current company
		const { message: activeSetting } = await frappe.call({
			method: "ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils.get_active_smart_settings",
			args: { doctype: settingsDoctypeName, company: frm.doc.company },
		});

		if (!activeSetting?.length) return;

		// --- Get RVAT Principals Button (Visible on Draft/New) ---
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Get RVAT Principals"),
				function () {
					getPrincipalsAction(activeSetting, frm);
				},
				__("Smart Actions")
			);
		}

		if (frm.doc.docstatus === 0 || frm.doc.prevent_vsdc_submission) return;

		// --- Send Invoice Button ---
		if (!frm.doc.custom_successfully_submitted) {
			frm.add_custom_button(
				__("Send Invoice"),
				function () {
					executeVSDCAction("Send Invoice", activeSetting, (settings_name) => ({
						method: "ca_erpnext_zra.ca_erpnext_zra.overrides.server.sales_invoice_override.send_invoice_details",
						args: { name: frm.doc.name, settings_name: settings_name },
						success_msg: "Invoice submission queued",
					}));
				},
				__("Smart Actions")
			);
		}

		// --- Sync Invoice Button ---
		if (frm.doc.custom_successfully_submitted || frm.doc.custom_vsdc_id) {
			frm.add_custom_button(
				__("Sync Invoice Details"),
				function () {
					executeVSDCAction("Sync Invoice", activeSetting, (settings_name) => ({
						method: "ca_erpnext_zra.ca_erpnext_zra.apis.invoice_processor.get_vsdc_invoice_details",
						args: {
							document_name: frm.doc.name,
							invoice_type: "Sales Invoice",
							settings_name: settings_name,
							company: frm.doc.company,
						},
						success_msg: "Invoice sync queued",
					}));
				},
				__("Smart Actions")
			);
		}

		// MTV Specific Query for Item Selection
		// Registered once in refresh - will re-evaluate on every search click based on frm.doc.custom_is_mtv
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			if (doc.custom_is_mtv) {
				return {
					filters: {
						"custom_vat_category_code": "B"
					}
				};
			}
			return {};
		});
	},

	validate: function (frm) {
		if (frm.doc.custom_is_mtv) {
			const non_b_items = (frm.doc.items || []).filter(item => item.custom_taxation_type !== 'B');
			if (non_b_items.length > 0) {
				const item_codes = non_b_items.map(i => i.item_code).join(', ');
				frappe.msgprint({
					title: __("Invalid Items for MTV"),
					message: __("MTV Sale is only allowed for items with Smart VAT Category Code 'B'. Non-B items found: {0}", [item_codes]),
					indicator: "red"
				});
				frappe.validated = false;
			}
		}
	},

	custom_is_mtv: function (frm) {
		// Set filter immediately
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			if (doc.custom_is_mtv) {
				return {
					filters: {
						"custom_vat_category_code": "B"
					}
				};
			}
			return {};
		});

		if (frm.doc.custom_is_mtv) {
			// Scan existing items
			let non_b_items = (frm.doc.items || []).filter(item => item.custom_taxation_type !== 'B');

			if (non_b_items.length) {
				frappe.confirm(
					__("MTV Mode Active. This invoice contains items that are not Category 'B'. MTV Sale requires all items to be Category 'B'. Would you like to remove non-B items?"),
					() => {
						// On Yes: Filter and remove
						let valid_items = (frm.doc.items || []).filter(item => item.custom_taxation_type === 'B');
						frm.set_value("items", []);
						valid_items.forEach(item => {
							let row = frm.add_child("items");
							$.extend(row, item);
						});
						frm.refresh_field("items");
						frappe.show_alert(__("Non-Category B items removed."));
					},
					() => {
						// On No: Uncheck to maintain data
						frm.set_value("custom_is_mtv", 0);
						frappe.show_alert(__("MTV Sale disabled to preserve items."));
					}
				);
			} else {
				frappe.show_alert({
					message: __("MTV Mode Active: Item selection filtered to Category 'B'."),
					indicator: "blue"
				});
			}
		}
		frm.refresh_field("items");
	},
});

// === Helper function: show settings modal if multiple, else call directly ===
function executeVSDCAction(title, settings, getCallArgs) {
	if (settings.length === 1) {
		const { method, args, success_msg } = getCallArgs(settings[0].name);
		frappe.call({
			method: method,
			args: args,
			callback: () => frappe.msgprint(__(success_msg)),
			error: (err) => {
				console.error(err);
				frappe.msgprint(__("An error occurred during the request."));
			},
		});
		return;
	}

	// If multiple settings exist, show selection dialog
	const dialog = new frappe.ui.Dialog({
		title: __(title),
		fields: [
			{
				label: __("Select VSDC Settings"),
				fieldname: "settings_name",
				fieldtype: "Select",
				options: settings.map((s) => ({
					label: `${s.company} (${s.name})`,
					value: s.name,
				})),
				reqd: 1,
				default: settings[0]?.name,
			},
		],
		primary_action_label: __("Proceed"),
		primary_action: ({ settings_name }) => {
			dialog.hide();
			const { method, args, success_msg } = getCallArgs(settings_name);
			frappe.call({
				method: method,
				args: args,
				callback: () => frappe.msgprint(__(success_msg)),
				error: (err) => {
					console.error(err);
					frappe.msgprint(__("An error occurred during the request."));
				},
			});
		},
	});
	dialog.show();
}

// === Child Doctype: Sales Invoice Item ===
frappe.ui.form.on(childDoctype, {
	item_code: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (row.item_code) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Item",
					name: row.item_code,
				},
				callback: function (r) {
					if (r.message) {
						if (!row.custom_taxation_type) {
							// Map Item's custom_vat_category_code to Sales Invoice Item's custom_taxation_type
							row.custom_taxation_type = r.message.custom_vat_category_code;
						}
						// Fetch RRP from Item's custom_rrp or fallback to standard_rate
						row.custom_rrp = r.message.custom_rrp || r.message.standard_rate || 0;
						frm.refresh_field("items");
					}
				},
			});
		}
	},
	custom_packaging_unit: async function (frm, cdt, cdn) {
		const packagingUnit = locals[cdt][cdn].custom_packaging_unit;
		if (packagingUnit) {
			frappe.db.get_value(
				packagingUnitDoctypeName,
				{ name: packagingUnit },
				["code"],
				(r) => {
					locals[cdt][cdn].custom_packaging_unit_code = r.code;
					frm.refresh_field("custom_packaging_unit_code");
				}
			);
		}
	},
	custom_unit_of_quantity: function (frm, cdt, cdn) {
		const unitOfQuantity = locals[cdt][cdn].custom_unit_of_quantity;
		if (unitOfQuantity) {
			frappe.db.get_value(
				unitOfQuantityDoctypeName,
				{ name: unitOfQuantity },
				["code"],
				(r) => {
					locals[cdt][cdn].custom_unit_of_quantity_code = r.code;
					frm.refresh_field("custom_unit_of_quantity_code");
				}
			);
		}
	},
});

// === Update Tax Amount Label dynamically ===
async function updateTaxAmountLabel(frm) {
	try {
		const defaultCompany = frappe.defaults.get_user_default("Company");
		if (!defaultCompany) return;

		const { message: companyDoc } = await frappe.db.get_value(
			"Company",
			defaultCompany,
			"default_currency"
		);
		if (companyDoc?.default_currency) {
			frm.fields_dict.items.grid.update_docfield_property(
				"custom_vat_amount",
				"label",
				`Tax Amount (${companyDoc.default_currency})`
			);
		}
	} catch (error) {

		console.error("Error updating Tax Amount label:", error);
	}
}

function getPrincipalsAction(settings, frm) {
	const handler = (settings_name) => {
		frappe.call({
			method: "ca_erpnext_zra.ca_erpnext_zra.apis.sales_api.get_principals",
			args: { settings_name: settings_name },
			callback: (r) => {
				if (r.message && r.message.data) {
					// r.message.data is expected to be the list of principals
					const principals = r.message.data.itemList || r.message.data;
					// Adjust based on actual API response structure. 
					// VSDC usually returns { resultCd, data: { itemList: [...] } } or similar

					// If it's a direct list
					let list = Array.isArray(principals) ? principals : [];

					// Fallback: check if the response itself is the list
					if (Array.isArray(r.message)) {
						list = r.message;
					}

					if (list.length === 0) {
						frappe.msgprint(__("No principals found."));
						return;
					}

					const d = new frappe.ui.Dialog({
						title: __("Select Principal"),
						fields: [
							{
								label: "Principal",
								fieldname: "principal",
								fieldtype: "Table",
								fields: [
									{ fieldname: "tpin", label: "TPIN", fieldtype: "Data", in_list_view: 1 },
									{ fieldname: "bhfId", label: "Branch ID", fieldtype: "Data", in_list_view: 1 },
									{ fieldname: "prncplNm", label: "Name", fieldtype: "Data", in_list_view: 1 }
								],
								data: list,
								get_data: () => list
							}
						],
						primary_action_label: __("Select"),
						primary_action: () => {
							// Table selection is tricky in standard Dialog. 
							// Better to use a Select field if list is small, or a custom HTML selection.
							// For simplicity, let's use a Select field populated with options.
							d.hide();
						}
					});

					// Re-implementing with Select for simplicity as Table selection in Dialog needs custom JS
					const options = list.map(p => ({
						label: `${p.prncplNm || p.tpin} (${p.tpin})`,
						value: p.tpin,
						original: p
					}));

					const selectionDialog = new frappe.ui.Dialog({
						title: __("Select Principal"),
						fields: [
							{
								label: __("Principal"),
								fieldname: "principal_tpin",
								fieldtype: "Select",
								options: options,
								reqd: 1
							}
						],
						primary_action_label: __("Set Principal"),
						primary_action: ({ principal_tpin }) => {
							const selected = options.find(o => o.value === principal_tpin).original;
							frm.set_value("custom_principal_id", selected.tpin);
							if (selected.prncplNm) {
								frm.set_value("custom_principal_name", selected.prncplNm);
							}
							selectionDialog.hide();
						}
					});

					selectionDialog.show();
				} else {
					console.log("Full response:", r);
					frappe.msgprint(__("No data received or invalid format. Check console."));
				}
			},
			error: (err) => {
				console.error(err);
				frappe.msgprint(__("Failed to fetch principals."));
			}
		});
	};

	if (settings.length === 1) {
		handler(settings[0].name);
	} else {
		const dialog = new frappe.ui.Dialog({
			title: __("Select VSDC Settings"),
			fields: [
				{
					label: __("Select VSDC Settings"),
					fieldname: "settings_name",
					fieldtype: "Select",
					options: settings.map((s) => ({
						label: `${s.company} (${s.name})`,
						value: s.name,
					})),
					reqd: 1,
					default: settings[0]?.name,
				},
			],
			primary_action_label: __("Proceed"),
			primary_action: ({ settings_name }) => {
				dialog.hide();
				handler(settings_name);
			},
		});
		dialog.show();
	}
}
