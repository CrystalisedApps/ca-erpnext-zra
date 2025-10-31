const itemDoctypeName = "Item";

frappe.ui.form.on(itemDoctypeName, {
  refresh: async function (frm) {
    if (frm.is_new()) return;

    // 🔹 Fetch Smart compliance data for this item
    const { message: data } = await frappe.call({
      method: "ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils.get_smart_action_data",
      args: {
        doctype: frm.doctype,
        docname: frm.doc.name,
      },
    });

    const allSettings = data?.settings || [];
    const registeredMappings = data?.registered_mappings || [];
    const unregisteredSettings = data?.unregistered_settings || [];

    if (!allSettings.length) return;

    const registered = data?.registered;

    // 🔹 For registered and unregistered items, show multi-company aware actions
    if (!frm.is_new()) {
      if (!registered) {
        // Show "Register Item" for unregistered companies
        const canRegister = unregisteredSettings.length > 0;
        if (canRegister) {
          frm.add_custom_button(
            __("Register Item (Smart)"),
            function () {
              showCompanySelectionModal(frm, "register_item", unregisteredSettings);
            },
            __("Smart Actions")
          );
        }
      } else {
        // Registered mappings found → enable fetch, update, inventory
        const mappedCompanies = registeredMappings.map((r) => ({
          name: r.smart_setup,
          company: getCompanyName(allSettings, r.smart_setup),
        }));

        frm.add_custom_button(
          __("Fetch Item Details (Smart)"),
          function () {
            showCompanySelectionModal(frm, "fetch_item_details", mappedCompanies);
          },
          __("Smart Actions")
        );

        frm.add_custom_button(
          __("Update Item (Smart)"),
          function () {
            showCompanySelectionModal(frm, "update_item", mappedCompanies);
          },
          __("Smart Actions")
        );

        if (frm.doc.is_stock_item && mappedCompanies.length) {
          frm.add_custom_button(
            __("Submit Item Inventory (Smart)"),
            function () {
              showCompanySelectionModal(frm, "submit_inventory", mappedCompanies);
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

// 🔹 Helper: Get company name from settings
function getCompanyName(allSettings, settingName) {
  const match = allSettings.find((s) => s.name === settingName);
  return match ? match.company : "Unknown";
}

// 🔹 Company selection modal
async function showCompanySelectionModal(frm, actionType, availableSettings) {
  if (!availableSettings.length) {
    frappe.msgprint(__("No available Smart settings for this action. Please check configuration."));
    return;
  }

  // If only one company available → skip dialog
  if (availableSettings.length === 1) {
    executeSmartItemAction(frm, actionType, availableSettings[0].name);
    return;
  }

  const options = availableSettings.map((setting) => ({
    label: `${setting.company} (${setting.name})`,
    value: setting.name,
  }));

  const dialog = new frappe.ui.Dialog({
    title: __("Select Company Setup"),
    fields: [
      {
        label: __("Select Smart Setup"),
        fieldname: "selected_settings_name",
        fieldtype: "Select",
        options: options,
        reqd: 1,
        default: options[0]?.value || null,
      },
    ],
    primary_action_label: __("Proceed"),
    primary_action: (data) => {
      const selectedSettingName = data.selected_settings_name;
      dialog.hide();
      executeSmartItemAction(frm, actionType, selectedSettingName);
    },
  });

  dialog.show();
}

// 🔹 Execute Smart API call per selected company
function executeSmartItemAction(frm, actionType, settingsName) {
  let method;
 

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
    args: { doc: frm.doc },
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
