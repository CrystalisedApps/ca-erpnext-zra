const doctype = "BOM";
const settingsDoctypeName = "Crystal ZRA Smart Invoice Settings";

frappe.ui.form.on(doctype, {
  refresh: async function (frm) {
    const companyName = frappe.boot.sysdefaults.company;
    const { message: activeSetting } = await frappe.call({
      method:
        "ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils.get_active_smart_settings",
      args: {
        doctype: settingsDoctypeName,
      },
    });

    if (activeSetting?.length > 0) {
      let itemCode;

      frappe.db.get_value("Item", { name: frm.doc.item }, ["*"], (response) => {
        itemCode = response.cusAtom_item_smart_code;
      });

      if (
        !frm.is_new() &&
        frm.doc.docstatus === 1 &&
        frm.doc.custom_item_composition_submitted_successfully != 1
      ) {
        frm.add_custom_button(
          __("Submit Item Composition"),
          function () {
            frappe.call({
              method:
                "ca_erpnext_zra.ca_erpnext_zra.apis.item_api.submit_item_composition",
              args: {
                document_name: frm.doc.name,
                branch: frm.doc.custom_smart_branch
              },
              freeze: true, // Freeze the screen
              freeze_message: __("Submitting item compositions to ZRA... Please wait."),
              callback: (response) => {
                frappe.show_alert({
                  message: __("Item compositions submitted successfully."),
                  indicator: "green",
                });
              },
              error: (r) => {
                frappe.msgprint({
                  title: __("Error"),
                  message: __("Failed to submit item compositions. Check logs."),
                  indicator: "red",
                });
              },
            });
          },
          __("Smart Actions")
        );
      }
    }
  },
});
