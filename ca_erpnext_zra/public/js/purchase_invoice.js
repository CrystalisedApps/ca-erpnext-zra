const purchaseParentDoctype = "Purchase Invoice";
const settingsDoctypeName = "Crystal ZRA Smart Invoice Settings";

frappe.ui.form.on(purchaseParentDoctype, {
	refresh: async function (frm) {
		// Fetch active Smart Zambia settings for this company
		const { message: activeSettings } = await frappe.call({
			method: "ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils.get_active_smart_settings",
			args: { company: frm.doc.company },
		});

		if (
			activeSettings?.length > 0 &&
			frm.doc.docstatus !== 0 &&
			!frm.doc.prevent_smart_submission
		) {
			// Add "Send to Smart" button if invoice not already submitted
			if (!frm.doc.custom_submitted_successfully) {
				frm.add_custom_button(
					__("Send invoice"),
					function () {
						showSmartSettingsModalAndExecute(
							"Send Purchase Invoice (Smart)",
							activeSettings,
							(settings_name) => ({
								method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.send_purchase_details",
								args: {
									doc: frm.doc,
									settings_name: settings_name,
								},
								success_msg:
									"Purchase invoice submission to Smart queued successfully.",
							})
						);
					},
					__("Smart Actions")
				);
			}

			// Optional: Fetch/Update actions if already submitted
			if (frm.doc.custom_submitted_successfully) {
				frm.add_custom_button(
					__("Fetch Smart Details"),
					function () {
						showSmartSettingsModalAndExecute(
							"Fetch Smart Invoice Details",
							activeSettings,
							(settings_name) => ({
								method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.fetch_purchase_details",
								args: {
									name: frm.doc.name,
									settings_name: settings_name,
								},
								success_msg: "Smart invoice details fetch queued successfully.",
							})
						);
					},
					__("Smart Actions")
				);

				frm.add_custom_button(
					__("Update Smart Invoice"),
					function () {
						showSmartSettingsModalAndExecute(
							"Update Smart Invoice",
							activeSettings,
							(settings_name) => ({
								method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.update_purchase_details",
								args: {
									name: frm.doc.name,
									settings_name: settings_name,
								},
								success_msg: "Smart invoice update queued successfully.",
							})
						);
					},
					__("Smart Actions")
				);
			}
		}
	},
});

// -------------------------------
// Helper: Show modal for company setup selection
// -------------------------------
function showSmartSettingsModalAndExecute(title, settings, getCallArgs) {
	if (settings.length === 1) {
		const { method, args, success_msg } = getCallArgs(settings[0].name);
		frappe.call({
			method,
			args,
			callback: () => frappe.msgprint(__(success_msg)),
			error: (err) => {
				console.error(err);
				frappe.msgprint(__("An error occurred during the Smart request."));
			},
		});
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __(title),
		fields: [
			{
				label: __("Select Smart Setup"),
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
				method,
				args,
				callback: () => frappe.msgprint(__(success_msg)),
				error: (err) => {
					console.error(err);
					frappe.msgprint(__("An error occurred during the Smart request."));
				},
			});
		},
	});

	dialog.show();
}
