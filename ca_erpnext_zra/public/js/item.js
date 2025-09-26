const itemDoctypName = "Item";

frappe.ui.form.on(itemDoctypName, {
  refresh: async function (frm) {
    if (frm.is_new()) return;

    // Fetch Smart compliance status for this item
    const { message: data } = await frappe.call({
      method: "ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils.get_smart_action_data",
      args: {
        doctype: frm.doctype,
        docname: frm.doc.name,
      },
    });
// console.log(data)
   const registered =data?.registered

    frm.smart_settings = data?.settings?.[0] || null;
    if (!frm.is_new()) {
      if (!registered) {
        // If not registered → show Register button
        frm.add_custom_button(
          __("Register Item (Smart)"),
          function () {
            executeSmartItemAction(frm, "register_item");
          },
          __("Smart Actions")
        );
      } else {
        // If already registered → allow fetch & update
        frm.add_custom_button(
          __("Fetch Item Details (Smart)"),
          function () {
            executeSmartItemAction(frm, "fetch_item_details");
          },
          __("Smart Actions")
        );

        frm.add_custom_button(
          __("Update Item (Smart)"),
          function () {
            executeSmartItemAction(frm, "update_item");
          },
          __("Smart Actions")
        );

        if (frm.doc.is_stock_item) {
          frm.add_custom_button(
            __("Submit Item Inventory (Smart)"),
            function () {
              executeSmartItemAction(frm, "submit_inventory");
            },
            __("Smart Actions")
          );
        }
      }
    }
  },

  // Optional: sync product type with stock flag
  custom_product_type_name: function (frm) {
    frm.set_value(
      "is_stock_item",
      frm.doc.custom_product_type_name !== "Service" ? 1 : 0
    );
  },
});

function executeSmartItemAction(frm, actionType) {
  let method;
  let args = {
  item_name: frm.doc.name,
  settings_name: frm.smart_settings?.name,
};

  switch (actionType) {
    case "register_item":
      method = "ca_erpnext_zra.ca_erpnext_zra.apis.item_api.perform_item_registration";
      break;

    case "fetch_item_details":
      method = "ca_erpnext_zra.ca_erpnext_zra.apis.item_api.fetch_item_details";
      break;

    case "update_item":
      method = "ca_erpnext_zra.ca_erpnext_zra.apis.item_api.update_item";
      break;

    case "submit_inventory":
      method = "ca_erpnext_zra.ca_erpnext_zra.apis.item_api.submit_inventory";
      break;

    default:
      frappe.msgprint(__("Unknown action type."));
      return;
  }

  frappe.call({
    method,
    args,
    callback: () => {
      const messages = {
        register_item: "Smart Item Registration Queued. Please check later.",
        fetch_item_details: "Smart Item Fetch Request Queued. Please check later.",
        update_item: "Smart Item Update Queued. Please check later.",
        submit_inventory: "Smart Inventory Submission Queued.",
      };
      frappe.msgprint(messages[actionType] || "Smart Request queued.");
    },
    error: (error) => {
      frappe.msgprint(__("An error occurred during the Smart request."));
      console.error(error);
    },
  });
}

