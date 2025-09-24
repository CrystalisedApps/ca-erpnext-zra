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
		frm.add_custom_button(
  __("Get Codes"),
  function () {
    frappe.call({
         method:
        "ca_erpnext_zra.ca_erpnext_zra.background_tasks.tasks.refresh_vsdc_codes",
      args: {
        settings_name: frm.doc.name,
        LastReqDt: frm.doc.LastReqDt || "", 
      },
      callback: (response) => {
        console.log("Full response:", response.message);

        if (
          response.message &&
          response.message.Result &&
          response.message.Result.data &&
          response.message.Result.data.clsList
        ) {
          console.log("Code Lists (clsList):", response.message.Result.data.clsList);
          frappe.msgprint(__("Code lists fetched. Check browser console for details."));
        } else {
          frappe.msgprint(__("No code lists found in response."));
        }

      },
      error: (error) => {
        // Error handling deferred to the server
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
