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

    if (frm.is_new()) return;

    // Fetch active VSDC settings for current company
    const { message: activeSetting } = await frappe.call({
      method: "ca_erpnext_zra.ca_erpnext_zra.utils.smart_api_utils.get_active_smart_settings",
      args: { doctype: settingsDoctypeName, company: frm.doc.company },
    });

    if (!activeSetting?.length || frm.doc.docstatus === 0 || frm.doc.prevent_vsdc_submission) return;

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

    // --- Verify and Fix Button ---
    frm.add_custom_button(
      __("Verify Submission and Fix if Incorrect"),
      function () {
        executeVSDCAction("Verify Submission", activeSetting, (settings_name) => ({
          method: "crystal_vsdc_integration.apis.apis.verify_invoice_details",
          args: {
            document_name: frm.doc.name,
            invoice_type: "Sales Invoice",
            settings_name: settings_name,
            company: frm.doc.company,
          },
          success_msg: "Verification and correction queued",
        }));
      },
      __("Smart Actions")
    );
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
        options: settings.map((s) => ({ label: `${s.company} (${s.name})`, value: s.name })),
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

    if (!row.custom_taxation_type && row.item_code) {
      frappe.call({
        method: "frappe.client.get",
        args: {
          doctype: "Item",
          name: row.item_code,
        },
        callback: function (r) {
          if (r.message) {
            row.custom_taxation_type = r.message.custom_taxation_type;
            row.custom_taxation_type_code = r.message.custom_taxation_type;
            frm.refresh_field("items");
          }
        },
      });
    }
  },
  custom_packaging_unit: async function (frm, cdt, cdn) {
    const packagingUnit = locals[cdt][cdn].custom_packaging_unit;
    if (packagingUnit) {
      frappe.db.get_value(packagingUnitDoctypeName, { name: packagingUnit }, ["code"], (r) => {
        locals[cdt][cdn].custom_packaging_unit_code = r.code;
        frm.refresh_field("custom_packaging_unit_code");
      });
    }
  },
  custom_unit_of_quantity: function (frm, cdt, cdn) {
    const unitOfQuantity = locals[cdt][cdn].custom_unit_of_quantity;
    if (unitOfQuantity) {
      frappe.db.get_value(unitOfQuantityDoctypeName, { name: unitOfQuantity }, ["code"], (r) => {
        locals[cdt][cdn].custom_unit_of_quantity_code = r.code;
        frm.refresh_field("custom_unit_of_quantity_code");
      });
    }
  },
});

// === Update Tax Amount Label dynamically ===
async function updateTaxAmountLabel(frm) {
  try {
    const defaultCompany = frappe.defaults.get_user_default("Company");
    if (!defaultCompany) return;

    const { message: companyDoc } = await frappe.db.get_value("Company", defaultCompany, "default_currency");
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
