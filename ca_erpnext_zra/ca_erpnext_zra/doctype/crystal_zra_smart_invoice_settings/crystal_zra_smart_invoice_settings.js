// Copyright (c) 2025, Brian Mwambia and contributors
// For license information, please see license.txt

frappe.ui.form.on("Crystal ZRA Smart Invoice Settings", {
	refresh(frm) {
		// Ping Server Button
		frm.add_custom_button(
			__("Ping Server"),
			function () {
				frappe.dom.freeze(__("Pinging Server... Please Wait"));
				frappe.call({
					method: "ca_erpnext_zra.ca_erpnext_zra.apis.healthcheck.ping_server",
					args: {
						settings: frm.doc.name,
					},
					callback: function (r) {
						frappe.dom.unfreeze();
						if (!r.exc) {
							// Optional: Add success message if needed
						}
					},
					error: function (err) {
						frappe.dom.unfreeze();
					},
				});
			},
			__("Smart Actions")
		);

		// Authenticate Button
		frm.add_custom_button(
			__("Authenticate"),
			function () {
				frappe.dom.freeze(__("Authenticating... Please Wait"));
				frappe.call({
					method: "ca_erpnext_zra.ca_erpnext_zra.apis.auth.authenticate",
					args: {
						settings_name: frm.doc.name,
					},
					callback: function (r) {
						frappe.dom.unfreeze();
						if (!r.exc) {
							frappe.msgprint(__("Authentication successful. Token updated."));
							frm.reload_doc();
						}
					},
					error: function (err) {
						frappe.dom.unfreeze();
					},
				});
			},
			__("Smart Actions")
		);

		// Get Codes Button
		frm.add_custom_button(
			__("Get Codes"),
			function () {
				frappe.dom.freeze(__("Refreshing Codes and Item Classifications... Please Wait"));
				frappe.call({
					method: "ca_erpnext_zra.ca_erpnext_zra.background_tasks.tasks.refresh_vsdc_codes",
					args: {
						settings_name: frm.doc.name,
						LastReqDt: frm.doc.LastReqDt || "",
					},
					callback: () => {
						frappe.call({
							method: "ca_erpnext_zra.ca_erpnext_zra.background_tasks.tasks.get_item_classification_codes",
							args: {
								settings_name: frm.doc.name,
								lastReqDt: "20231215000000",
							},
							callback: (r) => {
								frappe.dom.unfreeze();
								console.log("Raw API response:", r);
								frappe.msgprint(
									__("Codes and Item Classifications refreshed successfully.")
								);
							},
							error: function (err) {
								frappe.dom.unfreeze();
							},
						});
					},
					error: function (err) {
						frappe.dom.unfreeze();
					},
				});
			},
			__("Smart Actions")
		);

		// Initialize Device Button
		frm.add_custom_button(
			__("Initialize Device"),
			function () {
				frappe.dom.freeze(__("Initializing Device... Please Wait"));
				frappe.call({
					method: "ca_erpnext_zra.ca_erpnext_zra.apis.device.initialize_device",
					args: {
						settings_name: frm.doc.name,
						
					},
					callback: function (r) {
						frappe.dom.unfreeze();
						if (!r.exc) {
							frappe.msgprint(__("Device initialization successful."));
							frm.reload_doc();
						}
					},
					error: function (err) {
						frappe.dom.unfreeze();
					},
				});
			},
			__("Smart Actions")
		);
	},
});
