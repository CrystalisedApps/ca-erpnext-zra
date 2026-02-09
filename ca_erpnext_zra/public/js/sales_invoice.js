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

// --- Unified Handle for Sale Mode Toggling ---
async function handleSaleModeToggle(frm, modeName, vatCategoryCriteria) {
	// Fetch VAT categories from Item master
	const item_codes = (frm.doc.items || []).map(i => i.item_code);
	if (item_codes.length === 0) {
		frappe.show_alert({
			message: __("{0} Mode Active: {1}.", [modeName, getModeLabel(modeName)]),
			indicator: "blue"
		});
		return;
	}

	const { message } = await frappe.call({
		method: 'frappe.client.get_list',
		args: {
			doctype: 'Item',
			filters: [['name', 'in', item_codes]],
			fields: ['name', 'custom_vat_category_code']
		}
	});

	const vat_lookup = {};
	(message || []).forEach(item => {
		vat_lookup[item.name] = item.custom_vat_category_code;
	});

	// Check compliance using VAT category from Item master
	const nonCompliant = (frm.doc.items || []).filter(item => {
		const vat_cat = vat_lookup[item.item_code];
		return !vatCategoryCriteria(vat_cat);
	});

	if (nonCompliant.length > 0) {
		frappe.confirm(
			__("{0} Sale enabled. This invoice contains non-compliant items. {0} Sale requires {1}. Would you like to remove non-compliant items?", [modeName, getModeLabel(modeName)]),
			() => {
				const validItems = (frm.doc.items || []).filter(item => {
					const vat_cat = vat_lookup[item.item_code];
					return vatCategoryCriteria(vat_cat);
				});
				frm.set_value("items", []);
				validItems.forEach(item => {
					let row = frm.add_child("items");
					$.extend(row, item);
				});
				frm.refresh_field("items");
				frappe.show_alert(__("Non-compliant items removed."));
			},
			() => {
				// Revert checkbox
				const fieldName = `custom_is_${modeName.toLowerCase()}`;
				frm.set_value(fieldName, 0);
				frappe.show_alert(__("{0} Sale disabled to preserve items.", [modeName]));
			}
		);
	} else {
		frappe.show_alert({
			message: __("{0} Mode Active: {1}.", [modeName, getModeLabel(modeName)]),
			indicator: "blue"
		});
	}
}

function getModeLabel(modeName) {
	const modeLabels = {
		'MTV': __("Category 'B' items only"),
		'LPO': __("LPO-compliant items (C1, C2, C3) only"),
		'Exempt': __("Category C or D items only"),
		'Disbursement': __("Category 'E' items only"),
		'RVAT': __("RVAT items only")
	};
	return modeLabels[modeName] || "";
}

// === Parent Doctype: Sales Invoice ===
frappe.ui.form.on(parentDoctype, {
	refresh: async function (frm) {
		await updateTaxAmountLabel(frm);

		// MTV/LPO/Exempt/Disbursement Specific Query for Item Selection
		// Must be set early in refresh to apply to Drafts
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			if (doc.custom_is_mtv) {
				return { filters: { "custom_vat_category_code": "B", "custom_smart_item_code": ["!=", ""] } };
			} else if (doc.custom_is_lpo) {
				return { filters: { "custom_vat_category_code": ["in", ["C1", "C2", "C3"]], "custom_smart_item_code": ["!=", ""] } };
			} else if (doc.custom_is_exempt) {
				return { filters: { "custom_vat_category_code": ["in", ["C", "D"]], "custom_smart_item_code": ["!=", ""] } };
			} else if (doc.custom_is_disbursement) {
				return { filters: { "custom_vat_category_code": "E", "custom_smart_item_code": ["!=", ""] } };
			} else if (doc.custom_principal_id) {
				return { filters: { "custom_taxation_type": "RVAT", "custom_smart_item_code": ["!=", ""] } };
			}
			return {};
		});

		// Fetch active VSDC settings for current company
		const { message: activeSetting } = await frappe.call({
			method: "ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils.get_active_smart_settings",
			args: { doctype: settingsDoctypeName, company: frm.doc.company },
		});

		if (!activeSetting?.length) return;

		// --- Get RVAT Principals Button ---
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Get RVAT Principals"),
				function () {
					getPrincipalsAction(activeSetting, frm);
				},
				__("Smart Actions")
			);
		}

		// Only show submission/sync buttons for submitted invoices or specific cases
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
	},

	validate: async function (frm) {
		// Helper function to get VAT category from Item master
		const getItemVatCategories = async (item_codes) => {
			const { message } = await frappe.call({
				method: 'frappe.client.get_list',
				args: {
					doctype: 'Item',
					filters: [['name', 'in', item_codes]],
					fields: ['name', 'custom_vat_category_code']
				}
			});
			return message || [];
		};

		const item_codes = (frm.doc.items || []).map(i => i.item_code);
		if (item_codes.length === 0) return;

		const item_vat_map = await getItemVatCategories(item_codes);
		const vat_lookup = {};
		item_vat_map.forEach(item => {
			vat_lookup[item.name] = item.custom_vat_category_code;
		});

		// MTV Validation
		if (frm.doc.custom_is_mtv) {
			const non_b_items = (frm.doc.items || []).filter(item => vat_lookup[item.item_code] !== 'B');
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

		// LPO Validation
		if (frm.doc.custom_is_lpo) {
			if (!frm.doc.custom_lpo_number) {
				frappe.msgprint({
					title: __("LPO Number Required"),
					message: __("Please enter the LPO Number for this sale."),
					indicator: "red"
				});
				frappe.validated = false;
			}
			const non_lpo_items = (frm.doc.items || []).filter(item => !['C1', 'C2', 'C3'].includes(vat_lookup[item.item_code]));
			if (non_lpo_items.length > 0) {
				const item_codes = non_lpo_items.map(i => i.item_code).join(', ');
				frappe.msgprint({
					title: __("Invalid Items for LPO"),
					message: __("LPO Sale is only allowed for items with Smart VAT Category Code C1, C2, or C3. Non-compliant items found: {0}", [item_codes]),
					indicator: "red"
				});
				frappe.validated = false;
			}
		}

		// Exempt Validation
		if (frm.doc.custom_is_exempt) {
			const non_exempt_items = (frm.doc.items || []).filter(item => !['C', 'D'].includes(vat_lookup[item.item_code]));
			if (non_exempt_items.length > 0) {
				const item_codes = non_exempt_items.map(i => i.item_code).join(', ');
				frappe.msgprint({
					title: __("Invalid Items for Exempt Sale"),
					message: __("Exempt Sale is only allowed for items with Smart VAT Category Code C or D. Non-compliant items found: {0}", [item_codes]),
					indicator: "red"
				});
				frappe.validated = false;
			}
		}

		// Disbursement Validation
		if (frm.doc.custom_is_disbursement) {
			const non_e_items = (frm.doc.items || []).filter(item => vat_lookup[item.item_code] !== 'E');
			if (non_e_items.length > 0) {
				const item_codes = non_e_items.map(i => i.item_code).join(', ');
				frappe.msgprint({
					title: __("Invalid Items for Disbursement"),
					message: __("Disbursement Sale is only allowed for items with Smart VAT Category Code 'E'. Non-compliant items found: {0}", [item_codes]),
					indicator: "red"
				});
				frappe.validated = false;
			}
		}

		// RVAT Validation
		if (frm.doc.custom_principal_id) {
			const non_rvat_items = (frm.doc.items || []).filter(item => vat_lookup[item.item_code] !== 'RVAT');
			if (non_rvat_items.length > 0) {
				const item_codes = non_rvat_items.map(i => i.item_code).join(', ');
				frappe.msgprint({
					title: __("Invalid Items for RVAT Sale"),
					message: __("RVAT Sale (Principal ID set) is only allowed for items with Smart VAT Category Code 'RVAT'. Non-RVAT items found: {0}", [item_codes]),
					indicator: "red"
				});
				frappe.validated = false;
			}
		}
	},

	custom_is_mtv: function (frm) {
		if (frm.doc.custom_is_mtv) {
			// Uncheck others
			frm.set_value("custom_is_lpo", 0);
			frm.set_value("custom_is_exempt", 0);
			frm.set_value("custom_is_disbursement", 0);
			handleSaleModeToggle(frm, 'MTV', vat_cat => vat_cat === 'B');
		}
	},

	custom_is_lpo: function (frm) {
		if (frm.doc.custom_is_lpo) {
			// Uncheck others
			frm.set_value("custom_is_mtv", 0);
			frm.set_value("custom_is_exempt", 0);
			frm.set_value("custom_is_disbursement", 0);
			handleSaleModeToggle(frm, 'LPO', vat_cat => ['C1', 'C2', 'C3'].includes(vat_cat));
		}
	},

	custom_is_exempt: function (frm) {
		if (frm.doc.custom_is_exempt) {
			// Uncheck others
			frm.set_value("custom_is_mtv", 0);
			frm.set_value("custom_is_lpo", 0);
			frm.set_value("custom_is_disbursement", 0);
			handleSaleModeToggle(frm, 'Exempt', vat_cat => ['C', 'D'].includes(vat_cat));
		}
	},

	custom_is_disbursement: function (frm) {
		if (frm.doc.custom_is_disbursement) {
			// Uncheck others
			frm.set_value("custom_is_mtv", 0);
			frm.set_value("custom_is_lpo", 0);
			frm.set_value("custom_is_exempt", 0);
			handleSaleModeToggle(frm, 'Disbursement', vat_cat => vat_cat === 'E');
		}
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

							// Clear other sale modes to prevent conflict
							frm.set_value("custom_is_mtv", 0);
							frm.set_value("custom_is_lpo", 0);
							frm.set_value("custom_is_exempt", 0);
							frm.set_value("custom_is_disbursement", 0);

							frm.set_value("custom_principal_id", selected.tpin);
							if (selected.prncplNm) {
								frm.set_value("custom_principal_name", selected.prncplNm);
							}

							// Trigger cleanup logic for RVAT compliance
							handleSaleModeToggle(frm, 'RVAT', vat_cat => vat_cat === 'RVAT');

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
