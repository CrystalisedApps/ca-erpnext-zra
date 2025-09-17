// Copyright (c) 2025, Brian Mwambia and contributors
// For license information, please see license.txt

frappe.ui.form.on("Crystal ZRA Smart Invoice Settings", {
	refresh(frm) {
		// Ping Server Button
		frm.add_custom_button(
			__("Ping Server"),
			function () {
				frappe.call({
					method: "ca_erpnext_zra.ca_erpnext_zra.apis.healthcheck.ping_server",
					args: {
						settings: frm.doc.name,
					},
				});
			},
			__("Smart Actions")
		);
// Authenticate Button
		frm.add_custom_button(
			__("Authenticate"),
			function () {
				frappe.call({
					method: "ca_erpnext_zra.ca_erpnext_zra.apis.auth.authenticate",
					args: {
						settings_name: frm.doc.name,
					},
					callback: function (r) {
						if (!r.exc) {
							frappe.msgprint(__("Authentication successful. Token updated."));
							frm.reload_doc();
						}
					},
				});
			},
			__("Smart Actions")
		);
		//Initialize Device Button
		frm.add_custom_button(
			__("Initialize Device"),
			function () {
				frappe.call({
					method: "ca_erpnext_zra.ca_erpnext_zra.apis.device.initialize_device",
					args: {
						settings_name: frm.doc.name,
					},
					callback: function (r) {
						if (!r.exc) {
							frappe.msgprint(__("Device initialization successful."));
							frm.reload_doc();
						}
					},
				});
			},
			__("Smart Actions")
		);
	},
});
