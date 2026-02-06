// crystallised_zra_smart_purchases.js

const doctypeName = "Crystallised ZRA Smart Purchases";

frappe.ui.form.on(doctypeName, {
    onload: function (frm) {
        // Initialize registration type selection
        if (frm.is_new()) {
            frm.set_value("registration_type", "Automatic");
            frm.set_value("regtycd", "A");
            frm.set_value("purchase_status", "Approved");
            frm.set_value("pchssttscd", "02");
            frm.set_value("pchstycd", "N");
            frm.set_value("purchase_type", "Normal");
            frm.set_value("receipt_type", "Purchase");
            frm.set_value("receipt_type_code", "P");
            frm.set_value("payment_type_code", "01");
            frm.set_value("payment_type", "Cash");
        }

        // Setup standard Link field queries for supplier and branch fields
        setup_supplier_and_branch_queries(frm);
    },

    refresh(frm) {
        let companyName = frappe.boot.sysdefaults.company;

        // Toggle TPIN functionality based on registration type
        toggle_tpin_functionality(frm);

        // Update supplier TPIN field display to show TPIN instead of supplier name (handles both set and cleared states)
        if (is_tpin_functionality_enabled(frm)) {
            update_supplier_tpin_display(frm);
        }

        // Fallback if company not set
        if (!companyName) {
            frappe.call({
                method: "frappe.client.get_list",
                args: { doctype: "Company", fields: ["name"], limit_page_length: 1 },
                callback: function (res) {
                    if (res.message?.length) {
                        companyName = res.message[0].name;
                    }
                },
            });
        }

        // Setup item query for item_code field in items table
        setup_item_query(frm);

        // Setup manual TPIN entry handler (after form is fully loaded)
        setup_manual_tpin_entry_handler(frm);

        // Setup Clear Link button handlers
        setup_clear_link_handlers(frm);

        // Setup grid event listeners for item deletion
        setup_grid_event_listeners(frm);

        // Show item filtering status
        show_item_filtering_status(frm);

        // Monitor items array for changes (including deletions)
        monitor_items_changes(frm);


        if (!frm.is_new()) {


            frm.add_custom_button(
                __("Reject"),
                function () {
                    frappe.call({
                        method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.reject_purchase",
                        args: {
                            purchase_name: frm.doc.name,
                        },
                        callback: () => {
                            frappe.msgprint("Purchase Invoice has been rejected.");
                        },
                        freeze: true,
                        freeze_message: __("Rejecting Purchase Invoice..."),
                    });
                },
                __("Smart Actions")
            );
            // -------------------------------------------------------------
            // 🔹 1. CREATE SUPPLIER
            // -------------------------------------------------------------
            frm.add_custom_button(
                __("Create Supplier"),
                () => {
                    frappe.call({
                        method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_supplier_from_smart_purchase",
                        args: {
                            request_data: {
                                name: frm.doc.name,
                                company_name: companyName,
                                supplier_name: frm.doc.supplier_name,
                                supplier_tpin: frm.doc.supplier_tpin,
                                supplier_branch_id: frm.doc.supplier_branch_id,
                                supplier_country: "Zambia",
                                supplier_currency: "ZMW",
                            },
                        },
                    });
                },
                __("Smart Actions")
            );

            // -------------------------------------------------------------
            // 🔹 2. CREATE ITEMS
            // -------------------------------------------------------------
            frm.add_custom_button(
                __("Create Items"),
                () => {
                    frappe.call({
                        method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_items_from_smart_purchase",
                        args: {
                            request_data: {
                                name: frm.doc.name,
                                company_name: companyName,
                                items: frm.doc.items,
                            },
                        },
                    });
                },
                __("Smart Actions")
            );

            // -------------------------------------------------------------
            // CHECK IF ALL ITEMS ARE REGISTERED
            // -------------------------------------------------------------
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Item",
                    filters: {
                        item_code: ["in", frm.doc.items.map((i) => i.item_code)],
                    },
                    fields: ["name", "item_code", "custom_item_registered"],
                    limit_page_length: 999,
                },
                callback: function (res) {
                    let items = res.message || [];

                    // Count registered items
                    const unregistered_items = items.filter(
                        (i) => parseInt(i.custom_item_registered) !== 1
                    );

                    if (unregistered_items.length === 0) {
                        // -------------------------------------------------------------
                        //  All items registered → allow Purchase Invoice creation
                        // -------------------------------------------------------------
                        frm.add_custom_button(
                            __("Create Purchase Invoice"),
                            function () {
                                frappe.call({
                                    method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_purchase_invoice_from_smart_request",
                                    args: {
                                        request_data: {
                                            company_name: frm.doc.company,
                                            purchase_id: frm.doc.purchase_id,
                                            supplier_name: frm.doc.supplier_name,
                                            supplier_tpin: frm.doc.supplier_tpin,
                                            branch: frm.doc.branch,
                                            organisation: frm.doc.organisation,
                                            invoice_no: frm.doc.invoice_number,
                                            invoice_date: frm.doc.sales_date,
                                            items: frm.doc.items,

                                            // ZRA field mapping
                                            rcptTyCd: frm.doc.rcptTyCd,
                                            pchsTyCd: frm.doc.pchsTyCd,
                                            regTyCd: frm.doc.regTyCd,
                                            pchsSttsCd: frm.doc.pchsSttsCd,

                                            custom_receipt_type: frm.doc.custom_receipt_type,
                                            custom_registration_type:
                                                frm.doc.custom_registration_type,
                                            custom_purchase_type: frm.doc.custom_purchase_type,
                                            custom_purchase_status: frm.doc.custom_purchase_status,
                                        },
                                    },
                                    callback: () => {
                                        frappe.msgprint("Purchase Invoice has been created.");
                                    },
                                    freeze: true,
                                    freeze_message: __("Creating Purchase Invoice..."),
                                });
                            },
                            __("Smart Actions")
                        );
                    } else {
                        // -------------------------------------------------------------
                        // Some items are NOT registered
                        // -------------------------------------------------------------
                        let item_list = unregistered_items.map((i) => i.item_code).join(", ");

                        frm.set_intro(
                            __(
                                `The following items are not registered. Please register them before creating a Purchase Invoice:<br><b>${item_list}</b>`
                            ),
                            "red"
                        );
                    }
                },
            });

            // -------------------------------------------------------------
            // 🔹 3. CREATE PURCHASE INVOICE (COMMENTED OUT - KEEPING FOR REFERENCE)
            // -------------------------------------------------------------
            // frm.add_custom_button(
            //   __("Create Purchase Invoice"),
            //   () => {
            //     frappe.call({
            //       method:
            //         "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.create_purchase_invoice_from_smart_request",
            //       args: {
            //         request_data: {
            //           company_name: frm.doc.company,
            //           purchase_id: frm.doc.purchase_id,
            //           supplier_name: frm.doc.supplier_name,
            //           supplier_tpin: frm.doc.supplier_tpin,
            //           branch: frm.doc.branch,
            //           organisation: frm.doc.organisation,
            //           invoice_no: frm.doc.invoice_number,
            //           invoice_date: frm.doc.sales_date,
            //           items: frm.doc.items,

            //           // ZRA field mapping
            //           rcptTyCd: frm.doc.rcptTyCd,
            //           pchsTyCd: frm.doc.pchsTyCd,
            //           regTyCd: frm.doc.regTyCd,
            //           pchsSttsCd: frm.doc.pchsSttsCd,

            //           custom_receipt_type: frm.doc.custom_receipt_type,
            //           custom_registration_type:
            //             frm.doc.custom_registration_type,
            //           custom_purchase_type: frm.doc.custom_purchase_type,
            //           custom_purchase_status: frm.doc.custom_purchase_status,
            //         },
            //       },
            //     });
            //   },
            //   __("Smart Actions")
            // );

            // -------------------------------------------------------------
            // 🔹 4. FETCH SMART PURCHASE DETAILS FROM ZRA (COMMENTED OUT - KEEPING FOR REFERENCE)
            // -------------------------------------------------------------
            // frm.add_custom_button(
            // 	__("Fetch Smart Purchase Details"),
            // 	() => {
            // 		frappe.call({
            // 			method: "ca_erpnext_zra.ca_erpnext_zra.apis.smart_invoices.fetch_smart_purchase_details",
            // 			args: { request_data: { id: frm.doc.name, company_name: companyName } },
            // 		});
            // 	},
            // 	__("Smart Actions")
            // );

            // -------------------------------------------------------------
            // 🔹 5. APPROVE / REJECT PURCHASE (COMMENTED OUT - KEEPING FOR REFERENCE)
            // -------------------------------------------------------------

            // Show buttons only in Pending or empty state
            // if (!frm.doc.custom_purchase_status || frm.doc.custom_purchase_status === "Pending") {
            // 	frm.add_custom_button(
            // 		__("Approve Purchase"),
            // 		() => {
            // 			frappe.call({
            // 				method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.approve_smart_purchase",
            // 				args: { name: frm.doc.name },
            // 				callback: () => frm.reload_doc(),
            // 			});
            // 		},
            // 		__("Smart Workflow")
            // 	);

            // 	frm.add_custom_button(
            // 		__("Reject Purchase"),
            // 		() => {
            // 			frappe.call({
            // 				method: "ca_erpnext_zra.ca_erpnext_zra.apis.purchase_api.reject_smart_purchase",
            // 				args: { name: frm.doc.name },
            // 				callback: () => frm.reload_doc(),
            // 			});
            // 		},
            // 		__("Smart Workflow")
            // 	);
            // }



        }
    },

    // Field change handlers
    registration_type: function (frm) {
        update_registration_type_codes(frm);
        // Toggle TPIN functionality based on registration type
        toggle_tpin_functionality(frm);
        // Refresh item query when TPIN functionality changes
        setTimeout(() => setup_item_query(frm), 200);
        // Update item filtering status
        setTimeout(() => show_item_filtering_status(frm), 250);
    },

    purchase_type: function (frm) {
        update_purchase_type_codes(frm);
    },

    purchase_status: function (frm) {
        update_purchase_status_codes(frm);
    },

    payment_type: function (frm) {
        update_payment_type_codes(frm);
    },

    receipt_type: function (frm) {
        update_receipt_type_codes(frm);
    },

    // Supplier TPIN field change handler - auto-populate related fields
    supplier_tpin: function (frm) {
        // console.log("Supplier TPIN changed:", frm.doc.supplier_tpin);

        // Only work if TPIN functionality is enabled
        if (!is_tpin_functionality_enabled(frm)) {
            console.log("TPIN functionality disabled - skipping");
            return;
        }

        // Prevent cascading events during programmatic updates
        if (frm._updating_supplier_fields || frm._programmatic_change) {
            console.log("Skipping TPIN handler due to flags");
            return;
        }

        // Force blur to ensure field loses focus and change is properly registered
        setTimeout(() => {
            if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
                frm.fields_dict.supplier_tpin.$input.blur();
            }
        }, 50);

        if (frm.doc.supplier_tpin) {
            // Field has a value - populate related fields
            console.log("Populating from TPIN");
            populate_supplier_details_from_tpin(frm, frm.doc.supplier_tpin);
            // Update the display to show TPIN instead of supplier name
            setTimeout(() => update_supplier_tpin_display(frm), 150);
            // Refresh item query to filter by supplier
            setTimeout(() => setup_item_query(frm), 200);
            // Update item filtering status
            setTimeout(() => show_item_filtering_status(frm), 250);
        } else {
            // Field is cleared - clear related fields
            console.log("Clearing TPIN dependent fields");
            clear_supplier_dependent_fields(frm, 'tpin');
            // Reset item query to show all items
            setTimeout(() => setup_item_query(frm), 200);
            // Update item filtering status
            setTimeout(() => show_item_filtering_status(frm), 250);
        }
    },

    // Supplier name change handler - auto-populate related fields  
    supplier_name: function (frm) {
        console.log("Supplier Name changed:", frm.doc.supplier_name);

        // Prevent cascading events during programmatic updates
        if (frm._updating_supplier_fields || frm._programmatic_change) {
            console.log("Skipping Name handler due to flags");
            return;
        }

        // Force blur to ensure field loses focus and change is properly registered
        setTimeout(() => {
            if (frm.fields_dict.supplier_name && frm.fields_dict.supplier_name.$input) {
                frm.fields_dict.supplier_name.$input.blur();
            }
        }, 50);

        if (frm.doc.supplier_name) {
            // Field has a value - populate related fields
            console.log("Populating from Name");
            populate_supplier_details_from_name(frm, frm.doc.supplier_name);
            // Refresh item query to filter by supplier if TPIN functionality is enabled
            if (is_tpin_functionality_enabled(frm)) {
                setTimeout(() => setup_item_query(frm), 200);
                // Update item filtering status
                setTimeout(() => show_item_filtering_status(frm), 250);
            }
        } else {
            // Field is cleared - clear related fields
            console.log("Clearing Name dependent fields");
            clear_supplier_dependent_fields(frm, 'name');
            // Reset item query to show all items
            setTimeout(() => setup_item_query(frm), 200);
            // Update item filtering status
            setTimeout(() => show_item_filtering_status(frm), 250);
        }
    },

    // Branch field change handler - auto-populate supplier branch ID
    branch: function (frm) {
        // Branch field is not related to Supplier Branch ID
        // Supplier Branch ID comes from Supplier details, not Branch
        // This handler is kept for potential future use but does nothing for now
    },

    items_add: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row) {
            if (!row.quantity || row.quantity === 0) {
                row.quantity = 1;
            }
            // Add buttons to this new row functionality removed as requested
            calculate_item_row_safe(frm, row);
            calculate_totals(frm);
            frm.refresh_field("items");
        }
    },

    items_remove: function (frm, cdt, cdn) {
        // Multiple approaches to ensure totals are recalculated when items are deleted

        // Approach 1: Immediate recalculation
        calculate_totals(frm);

        // Approach 2: Delayed recalculation with multiple timeouts
        setTimeout(() => {
            calculate_totals(frm);
            frm.refresh_field("total_amount");
            frm.refresh_field("total_taxable_amount");
            frm.refresh_field("total_tax_amount");
            frm.refresh_field("total_item_count");
        }, 50);

        setTimeout(() => {
            calculate_totals(frm);
            frm.refresh_field("items");
        }, 200);

        setTimeout(() => {
            calculate_totals(frm);
            frm.dirty();
        }, 500);
    },

    // Add before_items_remove event
    before_items_remove: function (frm, cdt, cdn) {
        // This fires before the item is actually removed
        setTimeout(() => {
            calculate_totals(frm);
        }, 100);
    },

    after_save: function (frm) { },

    onload_post_render: function (frm) {
        // Additional setup after form is fully rendered
        setTimeout(() => {
            setup_grid_event_listeners(frm);
        }, 2000);
    }
});

// ============================================================
// CHILD TABLE EVENTS - Smart Registered Purchase Item
// ============================================================

frappe.ui.form.on("Smart Registered Purchase Item", {
    item_code: function (frm, cdt, cdn) {
        try {
            let row = frappe.get_doc(cdt, cdn);
            if (row && row.item_code && !row.__islocal_deleted && !row.__deleted) {
                // Fetch item details when item is selected
                fetch_item_details(frm, row);
            }
        } catch (error) {
            // Silently handle errors to prevent UI issues
            console.log("Error in item_code handler:", error);
        }
    },

    quantity: function (frm, cdt, cdn) {
        try {
            let row = frappe.get_doc(cdt, cdn);
            if (row && !row.__islocal_deleted && !row.__deleted) {
                calculate_item_row_safe(frm, row);
                frm.refresh_field("items");
                calculate_totals(frm);
            }
        } catch (error) {
            // Silently handle errors and just recalculate totals
            console.log("Error in quantity handler:", error);
            calculate_totals(frm);
        }
    },

    unit_price: function (frm, cdt, cdn) {
        try {
            let row = frappe.get_doc(cdt, cdn);
            if (row && !row.__islocal_deleted && !row.__deleted) {
                calculate_item_row_safe(frm, row);
                frm.refresh_field("items");
                calculate_totals(frm);
            }
        } catch (error) {
            // Silently handle errors and just recalculate totals
            console.log("Error in unit_price handler:", error);
            calculate_totals(frm);
        }
    },

    discount_rate: function (frm, cdt, cdn) {
        try {
            let row = frappe.get_doc(cdt, cdn);
            if (row && !row.__islocal_deleted && !row.__deleted) {
                calculate_item_row_safe(frm, row);
                frm.refresh_field("items");
                calculate_totals(frm);
            }
        } catch (error) {
            // Silently handle errors and just recalculate totals
            console.log("Error in discount_rate handler:", error);
            calculate_totals(frm);
        }
    },

    discount_amount: function (frm, cdt, cdn) {
        try {
            let row = frappe.get_doc(cdt, cdn);
            if (row && !row.__islocal_deleted && !row.__deleted) {
                calculate_item_row_safe(frm, row);
                frm.refresh_field("items");
                calculate_totals(frm);
            }
        } catch (error) {
            // Silently handle errors and just recalculate totals
            console.log("Error in discount_amount handler:", error);
            calculate_totals(frm);
        }
    },

    form_render: function (frm, cdt, cdn) { }
});

// ============================================================
// ITEM QUERY SETUP
// ============================================================

function setup_item_query(frm) {
    // Setup standard ERPNext item query for item_code field in items table
    // This enables the Link field functionality with search and filtering
    frm.set_query("item_code", "items", function (doc, cdt, cdn) {
        let filters = {
            'is_sales_item': 1,
            'is_purchase_item': 1,
            'disabled': 0
        };

        // If TPIN functionality is enabled and supplier is selected, try to filter items by supplier
        if (is_tpin_functionality_enabled(frm) && (frm.doc.supplier_tpin || frm.doc.supplier_name)) {
            const supplier_name = frm.doc.supplier_name || frm.doc.supplier_tpin;
            // Use our custom query which handles permissions and fallbacks internally
            return {
                query: "ca_erpnext_zra.queries.item_supplier_query",
                filters: {
                    'supplier': supplier_name,
                    'is_sales_item': 1,
                    'is_purchase_item': 1,
                    'disabled': 0
                }
            };
        }

        console.log("🔍 ITEM FILTERING DISABLED - Showing all items");
        console.log("🔍 TPIN Enabled:", is_tpin_functionality_enabled(frm), "Supplier Selected:", !!(frm.doc.supplier_tpin || frm.doc.supplier_name));

        // Default query without supplier filter
        return {
            query: "erpnext.controllers.queries.item_query",
            filters: filters
        };
    });
}

// ============================================================
// ITEM DETAILS FETCHING
// ============================================================

function fetch_item_details(frm, row) {
    if (!row || !row.item_code || row.__islocal_deleted) {
        return;
    }

    // Store the item_code to avoid accessing it from potentially undefined row later
    const item_code = row.item_code;

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Item",
            name: item_code
        },
        callback: function (response) {
            try {
                // Re-fetch the row to ensure it still exists
                const current_row = frappe.get_doc(row.doctype, row.name);

                if (response.message && current_row && !current_row.__islocal_deleted) {
                    const item = response.message;

                    // Set basic fields
                    current_row.item_name = item.item_name || item_code;
                    current_row.unit_price = item.standard_rate || item.valuation_rate || 0;
                    current_row.quantity_unit_code = item.stock_uom || 'Nos';

                    // Set custom fields if they exist
                    if (item.hasOwnProperty('custom_vat_category_code')) {
                        current_row.vat_category_code = item.custom_vat_category_code || 'A';
                    } else {
                        current_row.vat_category_code = 'A'; // Default
                    }

                    if (item.hasOwnProperty('custom_smart_item_classification_code')) {
                        current_row.item_class_code = item.custom_smart_item_classification_code || '';
                    } else {
                        current_row.item_class_code = '';
                    }

                    if (item.hasOwnProperty('custom_smart_packaging_unit')) {
                        current_row.packaging_unit_code = item.custom_smart_packaging_unit || '';
                    } else {
                        current_row.packaging_unit_code = '';
                    }

                    if (item.hasOwnProperty('custom_smart_quantity_unit')) {
                        current_row.quantity_unit_code = item.custom_smart_quantity_unit || current_row.quantity_unit_code;
                    }

                    // Set default quantity if not set
                    if (!current_row.quantity || current_row.quantity === 0) {
                        current_row.quantity = 1;
                    }

                    // Trigger calculation
                    calculate_item_row_safe(frm, current_row);
                    frm.refresh_field("items");
                    calculate_totals(frm);

                    frappe.show_alert({
                        message: __("Item '{0}' details loaded", [item_code]),
                        indicator: 'green'
                    });
                }
            } catch (error) {
                // Silently handle errors in callback
                console.log("Error in fetch_item_details callback:", error);
                calculate_totals(frm);
            }
        },
        error: function (err) {
            // Silently handle errors
            console.log("Error fetching item details:", err);
            calculate_totals(frm);
        }
    });
}

// ============================================================
// SUPPLIER AND BRANCH LINK FIELD SETUP
// ============================================================

function setup_supplier_and_branch_queries(frm) {
    // Setup query for supplier_tpin field (Link to Supplier) - Show TPIN with supplier name
    frm.set_query("supplier_tpin", function () {
        return {
            query: "ca_erpnext_zra.queries.supplier_tpin_query",
            filters: {
                "disabled": 0
            }
        };
    });

    // Add fallback query in case the custom query fails
    frm.fields_dict.supplier_tpin.get_query = function () {
        return {
            query: "ca_erpnext_zra.queries.supplier_tpin_query",
            filters: {
                "disabled": 0
            }
        };
    };

    // Setup query for supplier_name field (Link to Supplier)
    frm.set_query("supplier_name", function () {
        return {
            filters: {
                "disabled": 0
            }
        };
    });

    // Setup query for branch field (Link to Branch)
    frm.set_query("branch", function () {
        return {};
    });

    // Update supplier_tpin field display after form loads
    if (frm.doc.supplier_tpin) {
        update_supplier_tpin_display(frm);
    }
}

// Function to setup manual TPIN entry handler (called after form is fully loaded)
function setup_manual_tpin_entry_handler(frm) {
    // Add manual TPIN entry handler with safety check
    if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
        frm.fields_dict.supplier_tpin.$input.off('blur.manual_tpin');
        frm.fields_dict.supplier_tpin.$input.on('blur.manual_tpin', function () {
            const entered_value = $(this).val();
            if (entered_value && entered_value !== frm.doc.supplier_tpin) {
                // User manually entered a value, check if it's a TPIN
                if (entered_value.length >= 10) { // Assuming TPIN is at least 10 characters
                    search_supplier_by_tpin(frm, entered_value);
                }
            }
        });
    } else {
        // Fallback: Use a timeout to try again later
        setTimeout(() => {
            if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
                frm.fields_dict.supplier_tpin.$input.off('blur.manual_tpin');
                frm.fields_dict.supplier_tpin.$input.on('blur.manual_tpin', function () {
                    const entered_value = $(this).val();
                    if (entered_value && entered_value !== frm.doc.supplier_tpin) {
                        if (entered_value.length >= 10) {
                            search_supplier_by_tpin(frm, entered_value);
                        }
                    }
                });
            }
        }, 1000);
    }
}

// Function to setup Clear Link button handlers for better focus management
function setup_clear_link_handlers(frm) {
    // Handler for Supplier TPIN Clear Link button
    setTimeout(() => {
        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$wrapper) {
            frm.fields_dict.supplier_tpin.$wrapper.off('click.clear_tpin_link');
            frm.fields_dict.supplier_tpin.$wrapper.on('click.clear_tpin_link', '.link-btn', function (e) {
                console.log("TPIN Clear Link clicked");
                // Force blur on the field first
                if (frm.fields_dict.supplier_tpin.$input) {
                    frm.fields_dict.supplier_tpin.$input.blur();
                }

                // Small delay to ensure blur is processed, then clear dependent fields
                setTimeout(() => {
                    if (!frm.doc.supplier_tpin) { // Field was actually cleared
                        console.log("Clearing TPIN dependent fields");
                        clear_supplier_dependent_fields(frm, 'tpin');
                    }
                }, 150);
            });
        }

        // Handler for Supplier Name Clear Link button
        if (frm.fields_dict.supplier_name && frm.fields_dict.supplier_name.$wrapper) {
            frm.fields_dict.supplier_name.$wrapper.off('click.clear_name_link');
            frm.fields_dict.supplier_name.$wrapper.on('click.clear_name_link', '.link-btn', function (e) {
                console.log("Supplier Name Clear Link clicked");
                // Force blur on the field first
                if (frm.fields_dict.supplier_name.$input) {
                    frm.fields_dict.supplier_name.$input.blur();
                }

                // Small delay to ensure blur is processed, then clear dependent fields
                setTimeout(() => {
                    if (!frm.doc.supplier_name) { // Field was actually cleared
                        console.log("Clearing Name dependent fields");
                        clear_supplier_dependent_fields(frm, 'name');
                    }
                }, 150);
            });
        }

        // Alternative approach: Listen for any link button clicks in the form
        $(frm.wrapper).off('click.clear_links');
        $(frm.wrapper).on('click.clear_links', '.link-btn', function (e) {
            const $field_wrapper = $(this).closest('.frappe-control');
            const field_name = $field_wrapper.attr('data-fieldname');

            if (field_name === 'supplier_tpin') {
                console.log("Alternative TPIN clear detected");
                setTimeout(() => {
                    if (!frm.doc.supplier_tpin) {
                        clear_supplier_dependent_fields(frm, 'tpin');
                    }
                }, 200);
            } else if (field_name === 'supplier_name') {
                console.log("Alternative Name clear detected");
                setTimeout(() => {
                    if (!frm.doc.supplier_name) {
                        clear_supplier_dependent_fields(frm, 'name');
                    }
                }, 200);
            }
        });

    }, 1000); // Wait for form to be fully rendered
}

// Function to setup grid event listeners for better item deletion handling
function setup_grid_event_listeners(frm) {
    // Wait for the grid to be ready
    setTimeout(() => {
        if (frm.fields_dict.items && frm.fields_dict.items.grid) {
            const grid = frm.fields_dict.items.grid;

            // Listen for row removal events
            $(grid.wrapper).off('click.delete_row');
            $(grid.wrapper).on('click.delete_row', '.grid-delete-row', function () {
                // Delay calculation to ensure row is removed
                setTimeout(() => {
                    calculate_totals(frm);
                    frm.refresh_field("total_amount");
                    frm.refresh_field("total_taxable_amount");
                    frm.refresh_field("total_tax_amount");
                    frm.refresh_field("total_item_count");
                }, 200);
            });

            // Listen for any grid changes
            $(grid.wrapper).off('change.grid_totals');
            $(grid.wrapper).on('change.grid_totals', function () {
                setTimeout(() => {
                    calculate_totals(frm);
                }, 100);
            });

            // Override the grid's remove_row method
            if (grid.remove_row) {
                const original_remove_row = grid.remove_row;
                grid.remove_row = function (idx) {
                    const result = original_remove_row.call(this, idx);
                    // Recalculate after removal
                    setTimeout(() => {
                        calculate_totals(frm);
                        frm.refresh_field("total_amount");
                        frm.refresh_field("total_taxable_amount");
                        frm.refresh_field("total_tax_amount");
                        frm.refresh_field("total_item_count");
                    }, 100);
                    return result;
                };
            }
        }
    }, 1500);
}

// Function to monitor items array changes for total recalculation
function monitor_items_changes(frm) {
    // Store initial items count
    let previous_items_count = frm.doc.items ? frm.doc.items.length : 0;

    // Set up interval to check for changes
    const monitor_interval = setInterval(() => {
        if (!frm.doc || frm.doc.__islocal === 0) {
            // Form is saved or no longer exists, stop monitoring
            clearInterval(monitor_interval);
            return;
        }

        const current_items_count = frm.doc.items ? frm.doc.items.filter(item =>
            item && !item.__islocal_deleted && !item.__deleted && item.item_code
        ).length : 0;

        if (current_items_count !== previous_items_count) {
            // Items count changed, recalculate totals
            calculate_totals(frm);
            frm.refresh_field("total_amount");
            frm.refresh_field("total_taxable_amount");
            frm.refresh_field("total_tax_amount");
            frm.refresh_field("total_item_count");

            previous_items_count = current_items_count;
        }
    }, 500); // Check every 500ms

    // Store interval ID on form for cleanup
    frm._items_monitor_interval = monitor_interval;
}

// Function to check if TPIN functionality should be enabled
function is_tpin_functionality_enabled(frm) {
    return frm.doc.registration_type === "Automatic" && frm.doc.regtycd === "A";
}

// Function to toggle TPIN field visibility and functionality
function toggle_tpin_functionality(frm) {
    const enabled = is_tpin_functionality_enabled(frm);

    if (enabled) {
        // Show TPIN field and enable functionality
        frm.set_df_property("supplier_tpin", "hidden", 0);
        frm.set_df_property("supplier_tpin", "reqd", 0); // Optional, adjust as needed
    } else {
        // Hide TPIN field and clear its value
        frm.set_df_property("supplier_tpin", "hidden", 1);
        if (frm.doc.supplier_tpin) {
            frm.set_value("supplier_tpin", "", null, 1);
        }
        // Clear TPIN display
        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
            if (frm.fields_dict.supplier_tpin.$input.val() !== "") {
                frm.fields_dict.supplier_tpin.$input.val("");
            }
        }
        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.set_new_description) {
            frm.fields_dict.supplier_tpin.set_new_description("");
        }
    }

    return enabled;
}

// Function to clear supplier dependent fields when supplier fields are cleared
function clear_supplier_dependent_fields(frm, cleared_field) {
    console.log("clear_supplier_dependent_fields called with:", cleared_field);

    // Prevent cascading events and infinite loops
    if (frm._updating_supplier_fields) {
        console.log("Skipping clear due to _updating_supplier_fields flag");
        return;
    }

    frm._updating_supplier_fields = true;
    frm._programmatic_change = true;

    console.log("Setting flags and starting clear process");

    try {
        // Force blur on focused fields to ensure change events fire properly
        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
            frm.fields_dict.supplier_tpin.$input.blur();
        }
        if (frm.fields_dict.supplier_name && frm.fields_dict.supplier_name.$input) {
            frm.fields_dict.supplier_name.$input.blur();
        }

        // Small delay to allow blur events to process
        setTimeout(() => {
            // Clear ALL supplier-related fields regardless of which field was cleared
            console.log("Clearing all supplier-related fields");

            if (frm.doc.supplier_name) {
                console.log("Clearing supplier_name");
                frm.set_value("supplier_name", "");
            }

            if (frm.doc.supplier_tpin) {
                console.log("Clearing supplier_tpin");
                frm.set_value("supplier_tpin", "");
            }

            if (frm.doc.supplier_branch_id) {
                console.log("Clearing supplier_branch_id");
                frm.set_value("supplier_branch_id", "");
            }

            // Clear the TPIN field description and display
            if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.set_new_description) {
                frm.fields_dict.supplier_tpin.set_new_description("");
            }
            if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
                frm.fields_dict.supplier_tpin.$input.val("");
            }

            // Refresh item query to show all items when supplier is cleared
            setTimeout(() => setup_item_query(frm), 100);
            // Update item filtering status
            setTimeout(() => show_item_filtering_status(frm), 150);
        }, 100);

    } finally {
        // Reset the flags after a longer delay to ensure all events are processed
        setTimeout(() => {
            console.log("Resetting flags");
            frm._updating_supplier_fields = false;
            frm._programmatic_change = false;
        }, 600);
    }
}

// Function to update the display of supplier_tpin field to show TPIN instead of supplier name
function update_supplier_tpin_display(frm) {
    if (!frm.doc.supplier_tpin) {
        // Clear the field display and description if no supplier selected
        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
            frm.fields_dict.supplier_tpin.$input.val("");
        }
        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.set_new_description) {
            frm.fields_dict.supplier_tpin.set_new_description("");
        }
        return;
    }

    frappe.db.get_value("Supplier", frm.doc.supplier_tpin, "tax_id")
        .then(r => {
            if (r.message && r.message.tax_id) {
                // Update the field display to show TPIN with safety checks
                if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
                    frm.fields_dict.supplier_tpin.$input.val(r.message.tax_id);
                }
                if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.set_new_description) {
                    frm.fields_dict.supplier_tpin.set_new_description(`Supplier: ${frm.doc.supplier_tpin}`);
                }
            } else {
                // No TPIN found, clear the description
                if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.set_new_description) {
                    frm.fields_dict.supplier_tpin.set_new_description("");
                }
            }
        })
        .catch(err => {
            console.error("Error fetching supplier TPIN:", err);
            // Clear the description on error
            if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.set_new_description) {
                frm.fields_dict.supplier_tpin.set_new_description("");
            }
        });
}

// ============================================================
// AUTO-POPULATION FUNCTIONS
// ============================================================

function populate_supplier_details_from_tpin(frm, supplier_identifier) {
    if (!supplier_identifier) {
        clear_supplier_dependent_fields(frm, 'tpin');
        return;
    }

    // Prevent cascading events and infinite loops
    if (frm._updating_supplier_fields) return;
    frm._updating_supplier_fields = true;
    frm._programmatic_change = true;

    // First, try to get supplier by name (if it's a supplier name from dropdown)
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Supplier",
            name: supplier_identifier
        },
        callback: function (response) {
            try {
                if (response.message) {
                    const supplier = response.message;

                    // Update related fields
                    frm.set_value("supplier_name", supplier.name);

                    // Safely get branch details
                    get_supplier_branch_details(frm, supplier.name);

                    // Only show success message for manual TPIN entry, not dropdown selection
                    if (supplier_identifier.length >= 10) { // Likely a TPIN
                        frappe.show_alert({
                            message: __("Supplier found: {0}", [supplier.supplier_name]),
                            indicator: 'green'
                        });
                    }
                } else {
                    // If not found by name, try to search by TPIN
                    search_supplier_by_tpin(frm, supplier_identifier);
                }
            } finally {
                setTimeout(() => {
                    frm._updating_supplier_fields = false;
                    frm._programmatic_change = false;
                }, 500);
            }
        },
        error: function (err) {
            console.error("Error fetching supplier by name:", err);
            setTimeout(() => {
                frm._updating_supplier_fields = false;
                frm._programmatic_change = false;
            }, 500);
            // If error, try to search by TPIN
            search_supplier_by_tpin(frm, supplier_identifier);
        }
    });
}

function search_supplier_by_tpin(frm, tpin) {
    // Set programmatic change flag to prevent cascading events
    frm._programmatic_change = true;

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Supplier",
            filters: {
                "tax_id": tpin,
                "disabled": 0
            },
            fields: ["name", "supplier_name", "tax_id"],
            limit: 1
        },
        callback: function (response) {
            try {
                if (response.message && response.message.length > 0) {
                    const supplier = response.message[0];

                    // Update the supplier_tpin field to store the supplier name (for Link field)
                    frm.set_value("supplier_tpin", supplier.name);
                    frm.set_value("supplier_name", supplier.name);

                    // Try to get additional supplier details including branch info
                    get_supplier_branch_details(frm, supplier.name);

                    // Only show notification for successful TPIN search (manual entry)
                    frappe.show_alert({
                        message: __("Supplier found: {0}", [supplier.supplier_name]),
                        indicator: 'green'
                    });

                    // Update the display to show TPIN
                    setTimeout(() => update_supplier_tpin_display(frm), 100);
                } else {
                    // Only show error for manual TPIN entry
                    frappe.show_alert({
                        message: __("No supplier found with TPIN: {0}", [tpin]),
                        indicator: 'red'
                    });

                    // Clear related fields if supplier not found
                    clear_supplier_dependent_fields(frm, 'tpin');
                }
            } finally {
                setTimeout(() => {
                    frm._programmatic_change = false;
                }, 500);
            }
        },
        error: function (err) {
            console.error("Error searching supplier by TPIN:", err);
            frappe.show_alert({
                message: __("Error searching for supplier"),
                indicator: 'red'
            });

            // Clear related fields on error
            clear_supplier_dependent_fields(frm, 'tpin');

            setTimeout(() => {
                frm._programmatic_change = false;
            }, 500);
        }
    });
}

// Function to safely get supplier branch details
function get_supplier_branch_details(frm, supplier_name) {
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Supplier",
            name: supplier_name
        },
        callback: function (response) {
            if (response.message) {
                const supplier = response.message;

                // Check if custom_supplier_branch_id field exists and has a value
                if (supplier.hasOwnProperty('custom_supplier_branch_id') && supplier.custom_supplier_branch_id) {
                    frm.set_value("supplier_branch_id", supplier.custom_supplier_branch_id);
                } else {
                    // Clear the field if no branch ID is available
                    frm.set_value("supplier_branch_id", "");
                }
            }
        },
        error: function (err) {
            console.error("Error fetching supplier branch details:", err);
            // Don't show error to user for this optional field
            frm.set_value("supplier_branch_id", "");
        }
    });
}

function populate_supplier_details_from_name(frm, supplier_name) {
    if (!supplier_name) {
        clear_supplier_dependent_fields(frm, 'name');
        return;
    }

    // Prevent cascading events and infinite loops
    if (frm._updating_supplier_fields) return;
    frm._updating_supplier_fields = true;
    frm._programmatic_change = true;

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Supplier",
            name: supplier_name
        },
        callback: function (response) {
            try {
                if (response.message) {
                    const supplier = response.message;

                    // Only populate TPIN field if functionality is enabled AND supplier has a tax_id
                    if (is_tpin_functionality_enabled(frm) && supplier.tax_id && supplier.tax_id.trim()) {
                        frm.set_value("supplier_tpin", supplier.name);
                        // Update the display to show TPIN instead of supplier name
                        setTimeout(() => update_supplier_tpin_display(frm), 100);
                    } else {
                        // Clear TPIN field if functionality is disabled or supplier has no tax_id
                        if (frm.doc.supplier_tpin) {
                            frm.set_value("supplier_tpin", "");
                        }
                        // Clear TPIN display
                        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.$input) {
                            frm.fields_dict.supplier_tpin.$input.val("");
                        }
                        if (frm.fields_dict.supplier_tpin && frm.fields_dict.supplier_tpin.set_new_description) {
                            frm.fields_dict.supplier_tpin.set_new_description("");
                        }
                    }

                    // Always try to get branch details from supplier
                    get_supplier_branch_details(frm, supplier.name);

                    // No notification for dropdown selection - it's expected behavior
                } else {
                    // Clear related fields if supplier not found
                    clear_supplier_dependent_fields(frm, 'name');
                }
            } finally {
                setTimeout(() => {
                    frm._updating_supplier_fields = false;
                    frm._programmatic_change = false;
                }, 500);
            }
        },
        error: function (err) {
            console.error("Error fetching supplier details:", err);
            setTimeout(() => {
                frm._updating_supplier_fields = false;
                frm._programmatic_change = false;
            }, 500);
            // Clear related fields on error
            clear_supplier_dependent_fields(frm, 'name');
        }
    });
}

function populate_branch_details(frm, branch_name) {
    if (!branch_name) {
        // Clear supplier branch ID if no branch selected
        frm.set_value("supplier_branch_id", "");
        return;
    }

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Branch",
            name: branch_name
        },
        callback: function (response) {
            if (response.message) {
                const branch = response.message;

                // Always update supplier branch ID
                frm.set_value("supplier_branch_id", branch.custom_branch_code || "");

                frappe.show_alert({
                    message: __("Branch details populated: {0}", [branch.branch || branch.name]),
                    indicator: 'green'
                });
            } else {
                // Clear supplier branch ID if branch not found
                frm.set_value("supplier_branch_id", "");
            }
        },
        error: function (err) {
            console.error("Error fetching branch details:", err);
            // Clear supplier branch ID on error
            frm.set_value("supplier_branch_id", "");
        }
    });
}

function load_supplier_details(frm) {
    if (!frm.doc.supplier_tpin && !frm.doc.supplier_name) {
        frappe.msgprint(__("Please enter a Supplier TPIN or Name first"));
        return;
    }

    let identifier = frm.doc.supplier_tpin || frm.doc.supplier_name;
    let searchType = frm.doc.supplier_tpin ? 'tpin' : 'name';

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Supplier",
            filters: searchType === 'tpin' ?
                { "tax_id": identifier, "disabled": 0 } :
                { "supplier_name": identifier, "disabled": 0 },
            fields: ["name", "supplier_name", "tax_id", "supplier_group", "country",
                "mobile_no", "email_id", "primary_address", "website", "supplier_details"],
            limit: 1
        },
        callback: function (response) {
            if (response.message && response.message.length > 0) {
                const supplier = response.message[0];

                // Get additional details including branch info safely
                get_supplier_additional_details(supplier, frm);
            } else {
                frappe.msgprint(__("No supplier found with the provided information"));
            }
        },
        error: function (err) {
            console.error("Error loading supplier details:", err);
            frappe.msgprint(__("Error loading supplier details"));
        }
    });
}

// Function to get additional supplier details and show dialog
function get_supplier_additional_details(supplier, frm) {
    // Try to get branch details safely
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Supplier",
            name: supplier.name
        },
        callback: function (response) {
            let branch_id = "";
            if (response.message && response.message.hasOwnProperty('custom_supplier_branch_id')) {
                branch_id = response.message.custom_supplier_branch_id || 'N/A';
            } else {
                branch_id = 'N/A';
            }

            // Show supplier details in a dialog
            const supplierDetails = `
                <div style="max-height: 400px; overflow-y: auto;">
                    <h4>${supplier.supplier_name}</h4>
                    <table class="table table-bordered">
                        <tr>
                            <td style="width: 30%;"><strong>TPIN:</strong></td>
                            <td>${supplier.tax_id || 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Supplier Group:</strong></td>
                            <td>${supplier.supplier_group || 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Country:</strong></td>
                            <td>${supplier.country || 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Mobile:</strong></td>
                            <td>${supplier.mobile_no || 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Email:</strong></td>
                            <td>${supplier.email_id || 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Supplier Branch ID:</strong></td>
                            <td>${branch_id}</td>
                        </tr>
                        <tr>
                            <td><strong>Primary Address:</strong></td>
                            <td>${supplier.primary_address || 'N/A'}</td>
                        </tr>
                        <tr>
                            <td><strong>Website:</strong></td>
                            <td>${supplier.website || 'N/A'}</td>
                        </tr>
                        ${supplier.supplier_details ? `
                        <tr>
                            <td><strong>Details:</strong></td>
                            <td>${supplier.supplier_details}</td>
                        </tr>
                        ` : ''}
                    </table>
                </div>
            `;

            const d = new frappe.ui.Dialog({
                title: __('Supplier Details'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'supplier_html',
                        options: supplierDetails
                    }
                ],
                primary_action_label: __('Close'),
                primary_action(values) {
                    d.hide();
                }
            });

            d.show();

            frappe.show_alert({
                message: __("Supplier details loaded successfully"),
                indicator: 'green'
            });
        },
        error: function (err) {
            console.error("Error getting additional supplier details:", err);
            // Still show dialog with basic info
            show_basic_supplier_dialog(supplier);
        }
    });
}

// Fallback function to show basic supplier info
function show_basic_supplier_dialog(supplier) {
    const supplierDetails = `
        <div style="max-height: 400px; overflow-y: auto;">
            <h4>${supplier.supplier_name}</h4>
            <table class="table table-bordered">
                <tr>
                    <td style="width: 30%;"><strong>TPIN:</strong></td>
                    <td>${supplier.tax_id || 'N/A'}</td>
                </tr>
                <tr>
                    <td><strong>Supplier Group:</strong></td>
                    <td>${supplier.supplier_group || 'N/A'}</td>
                </tr>
                <tr>
                    <td><strong>Country:</strong></td>
                    <td>${supplier.country || 'N/A'}</td>
                </tr>
                <tr>
                    <td><strong>Mobile:</strong></td>
                    <td>${supplier.mobile_no || 'N/A'}</td>
                </tr>
                <tr>
                    <td><strong>Email:</strong></td>
                    <td>${supplier.email_id || 'N/A'}</td>
                </tr>
            </table>
        </div>
    `;

    const d = new frappe.ui.Dialog({
        title: __('Supplier Details'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'supplier_html',
                options: supplierDetails
            }
        ],
        primary_action_label: __('Close'),
        primary_action(values) {
            d.hide();
        }
    });

    d.show();
}

// ============================================================
// LOAD BRANCH DETAILS FUNCTION
// ============================================================

function load_branch_details(frm) {
    if (!frm.doc.branch) {
        frappe.msgprint(__("Please select a Branch first"));
        return;
    }

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Branch",
            name: frm.doc.branch
        },
        callback: function (response) {
            if (response.message) {
                const branch = response.message;

                // Show branch details in a dialog
                const branchDetails = `
                    <div style="max-height: 400px; overflow-y: auto;">
                        <h4>${branch.branch || branch.name}</h4>
                        <table class="table table-bordered">
                            <tr>
                                <td style="width: 30%;"><strong>Branch Code:</strong></td>
                                <td>${branch.custom_branch_code || 'N/A'}</td>
                            </tr>
                            <tr>
                                <td><strong>Address:</strong></td>
                                <td>${branch.address || 'N/A'}</td>
                            </tr>
                            <tr>
                                <td><strong>Contact Number:</strong></td>
                                <td>${branch.contact_number || 'N/A'}</td>
                            </tr>
                        </table>
                    </div>
                `;

                const d = new frappe.ui.Dialog({
                    title: __('Branch Details'),
                    fields: [
                        {
                            fieldtype: 'HTML',
                            fieldname: 'branch_html',
                            options: branchDetails
                        }
                    ],
                    primary_action_label: __('Close'),
                    primary_action(values) {
                        d.hide();
                    }
                });

                d.show();
            } else {
                frappe.msgprint(__("Branch not found"));
            }
        },
        freeze: true,
        freeze_message: __("Loading branch details..."),
        error: function (err) {
            console.error("Error loading branch details:", err);
        }
    });
}


// ============================================================
// ZRA ITEM LOADING FUNCTIONS
// ============================================================

function load_zra_smart_purchase_items(frm) {
    console.log("Loading ZRA smart purchase items...");

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Crystallised ZRA Smart Purchases",
            name: frm.doc.name
        },
        callback: function (response) {
            if (response.message && response.message.items) {
                const items = response.message.items;
                console.log("✓ ZRA Items loaded:", items.length);

                if (items.length > 0) {
                    frm.clear_table("items");

                    items.forEach((item, index) => {
                        let row = frm.add_child("items");

                        // Copy all fields from ZRA item
                        Object.keys(item).forEach(key => {
                            if (key !== 'name' && key !== 'parent' && key !== 'parentfield' && key !== 'parenttype' && key !== 'idx') {
                                row[key] = item[key];
                            }
                        });

                        // Ensure item_seq
                        if (!row.item_seq) {
                            row.item_seq = index + 1;
                        }

                        // Calculate this row
                        calculate_item_row_safe(frm, row);
                    });

                    frm.refresh_field("items");
                    calculate_totals(frm);

                    frappe.show_alert({
                        message: __("Loaded {0} ZRA items", [items.length]),
                        indicator: 'green'
                    });
                } else {
                    frappe.show_alert({
                        message: __("No items found in this ZRA purchase"),
                        indicator: 'orange'
                    });
                }
            }
        },
        error: function (err) {
            console.error("ERROR loading ZRA items:", err);
            frappe.show_alert({
                message: __("Failed to load ZRA items"),
                indicator: 'red'
            });
        },
        freeze: true,
        freeze_message: __("Loading ZRA items...")
    });
}

// ============================================================
// CALCULATION FUNCTIONS
// ============================================================

// SAFE version of calculate_item_row that checks for null row
function calculate_item_row_safe(frm, row) {
    // Enhanced safety checks
    if (!row || typeof row !== 'object') {
        return;
    }

    // Check if row is marked for deletion
    if (row.__islocal_deleted || row.__deleted) {
        return;
    }

    // Check if row has minimum required properties
    if (!row.hasOwnProperty('name') && !row.hasOwnProperty('idx')) {
        return;
    }

    // Ensure required fields exist with defaults
    if (!row.hasOwnProperty('quantity') || row.quantity === null || row.quantity === undefined) {
        row.quantity = 0;
    }
    if (!row.hasOwnProperty('unit_price') || row.unit_price === null || row.unit_price === undefined) {
        row.unit_price = 0;
    }
    if (!row.hasOwnProperty('supply_amount') || row.supply_amount === null || row.supply_amount === undefined) {
        row.supply_amount = 0;
    }
    if (!row.hasOwnProperty('discount_rate') || row.discount_rate === null || row.discount_rate === undefined) {
        row.discount_rate = 0;
    }
    if (!row.hasOwnProperty('discount_amount') || row.discount_amount === null || row.discount_amount === undefined) {
        row.discount_amount = 0;
    }
    if (!row.hasOwnProperty('vat_amount') || row.vat_amount === null || row.vat_amount === undefined) {
        row.vat_amount = 0;
    }
    if (!row.hasOwnProperty('total_amount') || row.total_amount === null || row.total_amount === undefined) {
        row.total_amount = 0;
    }
    if (!row.hasOwnProperty('vat_category_code') || !row.vat_category_code) {
        row.vat_category_code = 'A';
    }

    // Convert to numbers
    const quantity = parseFloat(row.quantity) || 0;
    const unit_price = parseFloat(row.unit_price) || 0;
    const discount_rate = parseFloat(row.discount_rate) || 0;

    // Calculate supply amount
    if (quantity && unit_price) {
        row.supply_amount = quantity * unit_price;
    } else {
        row.supply_amount = 0;
    }

    // Calculate discount amount if discount rate is provided
    if (discount_rate && row.supply_amount) {
        row.discount_amount = (row.supply_amount * discount_rate) / 100;
    } else {
        row.discount_amount = 0;
    }

    // Calculate taxable amount (supply - discount)
    const supply_amount = parseFloat(row.supply_amount) || 0;
    const discount_amount = parseFloat(row.discount_amount) || 0;
    let taxable_amount = supply_amount - discount_amount;
    if (taxable_amount < 0) taxable_amount = 0;

    // Calculate VAT based on vat_category_code
    let vat_rate = 0.16; // Default 16% for Zambia

    // Adjust VAT rate based on category code
    if (row.vat_category_code === 'TOT') {
        vat_rate = 0.00; // Turn Over Tax (0%)
    } else if (row.vat_category_code === 'E') {
        vat_rate = 0.00; // Disbursement (0%)
    } else if (row.vat_category_code === 'RVAT') {
        vat_rate = 0.16; // Reverse VAT (16%)
    } else if (row.vat_category_code === 'D') {
        vat_rate = 0.00; // Exempt
    } else if (row.vat_category_code === 'C3') {
        vat_rate = 0.00; // Zero Rated (0%)
    } else if (row.vat_category_code === 'C2') {
        vat_rate = 0.00; // Zero-rating LPO (0%)
    } else if (row.vat_category_code === 'C1') {
        vat_rate = 0.00; // Exports (0%)
    } else if (row.vat_category_code === 'B') {
        vat_rate = 0.16; // Minimum Taxable Value (MTV-16%)
    } else if (row.vat_category_code === 'A') {
        vat_rate = 0.16; // Standard Rated (16%)
    }

    row.vat_amount = taxable_amount * vat_rate;
    row.total_amount = taxable_amount + row.vat_amount;

    // Round to 2 decimal places
    row.supply_amount = parseFloat(row.supply_amount.toFixed(2));
    row.discount_amount = parseFloat(row.discount_amount.toFixed(2));
    row.vat_amount = parseFloat(row.vat_amount.toFixed(2));
    row.total_amount = parseFloat(row.total_amount.toFixed(2));
}

// Function to calculate totals with safety checks
function calculate_totals(frm) {
    if (!frm.doc.items || !Array.isArray(frm.doc.items)) {
        frm.set_value("total_amount", 0);
        frm.set_value("total_taxable_amount", 0);
        frm.set_value("total_tax_amount", 0);
        frm.set_value("total_item_count", 0);
        return;
    }

    let total_amount = 0;
    let total_taxable_amount = 0;
    let total_tax_amount = 0;
    let total_item_count = 0;

    // Filter out null/undefined items, deleted items, and items marked for deletion
    const validItems = frm.doc.items.filter(item =>
        item &&
        !item.__islocal_deleted &&
        !item.__deleted &&
        item.item_code // Must have an item code to be valid
    );

    validItems.forEach(function (item) {
        total_item_count += 1;

        // Use parsed values
        const supply_amount = parseFloat(item.supply_amount) || 0;
        const discount_amount = parseFloat(item.discount_amount) || 0;
        const vat_amount = parseFloat(item.vat_amount) || 0;
        const item_total = parseFloat(item.total_amount) || 0;

        total_amount += item_total;
        total_taxable_amount += (supply_amount - discount_amount);
        total_tax_amount += vat_amount;
    });

    // Only set values if they actually changed to avoid marking form as dirty/Not Saved
    if (flt(frm.doc.total_amount, 2) !== total_amount) {
        frm.set_value("total_amount", total_amount, null, 1);
    }
    if (flt(frm.doc.total_taxable_amount, 2) !== total_taxable_amount) {
        frm.set_value("total_taxable_amount", total_taxable_amount, null, 1);
    }
    if (flt(frm.doc.total_tax_amount, 2) !== total_tax_amount) {
        frm.set_value("total_tax_amount", total_tax_amount, null, 1);
    }
    if (frm.doc.total_item_count !== total_item_count) {
        frm.set_value("total_item_count", total_item_count, null, 1);
    }
}

// ============================================================
// HELPER FUNCTIONS
// ============================================================

function format_currency(value, currency) {
    if (!value) value = 0;
    return frappe.format(value, { fieldtype: "Currency", options: currency || "ZMW" });
}

// ============================================================
// FIELD MAPPING FUNCTIONS
// ============================================================

// Function to update registration type codes
function update_registration_type_codes(frm) {
    let registration_type = frm.doc.registration_type;
    let target_val = "";
    if (registration_type === "Manual") {
        target_val = "M";
    } else if (registration_type === "Automatic") {
        target_val = "A";
    }

    if (target_val && frm.doc.regtycd !== target_val) {
        frm.set_value("regtycd", target_val, null, 1);
    }
}

// Function to update purchase type codes
function update_purchase_type_codes(frm) {
    let purchase_type = frm.doc.purchase_type;
    let target_val = "";
    if (purchase_type === "Normal") {
        target_val = "N";
    } else if (purchase_type === "Copy") {
        target_val = "C";
    }

    if (target_val && frm.doc.pchstycd !== target_val) {
        frm.set_value("pchstycd", target_val, null, 1);
    }
}

// Function to update receipt type codes
function update_receipt_type_codes(frm) {
    let receipt_type = frm.doc.receipt_type;
    let target_val = "";
    if (receipt_type === "Purchase") {
        target_val = "P";
    } else if (receipt_type === "Refund after Purchase") {
        target_val = "R";
    }

    if (target_val && frm.doc.receipt_type_code !== target_val) {
        frm.set_value("receipt_type_code", target_val, null, 1);
    }
}

// Function to update purchase status codes
function update_purchase_status_codes(frm) {
    let purchase_status = frm.doc.purchase_status;
    let target_val = "";
    if (purchase_status === "Refunded") {
        target_val = "05";
    } else if (purchase_status === "Transferred") {
        target_val = "06";
    } else if (purchase_status === "Approved") {
        target_val = "02";
    } else if (purchase_status === "Rejected") {
        target_val = "04";
    }

    if (target_val && frm.doc.pchssttscd !== target_val) {
        frm.set_value("pchssttscd", target_val, null, 1);
    }
}

// Function to update payment type codes
function update_payment_type_codes(frm) {
    let payment_type = frm.doc.payment_type;
    const paymentTypeMap = {
        "Cash": "01",
        "Credit": "02",
        "Cash/Credit": "03",
        "Bank Check": "04",
        "Debit&Credit Card": "05",
        "Mobile Money": "06",
        "Other": "07",
        "Bank transfer": "08",
    };

    let target_val = paymentTypeMap[payment_type];
    if (target_val && frm.doc.payment_type_code !== target_val) {
        frm.set_value("payment_type_code", target_val, null, 1);
    }
}

function view_item_details(item_code) {
    // Open the Item doctype in a new form
    frappe.set_route('Form', 'Item', item_code);
}

// ============================================================
// ITEM FILTERING STATUS FUNCTION
// ============================================================

function show_item_filtering_status(frm) {
    // Show user when item filtering is active
    if (is_tpin_functionality_enabled(frm) && (frm.doc.supplier_tpin || frm.doc.supplier_name)) {
        const supplier_name = frm.doc.supplier_name || frm.doc.supplier_tpin;

        // Get supplier display name for better UX
        frappe.db.get_value("Supplier", supplier_name, "supplier_name")
            .then(res => {
                if (res.message && res.message.supplier_name) {
                    frm.set_intro(
                        __("Items are filtered to show only those supplied by: <strong>{0}</strong>. If no items appear, this supplier may not have any linked items.", [res.message.supplier_name]),
                        "blue"
                    );
                    // Auto-hide intro after 5 seconds
                    setTimeout(() => {
                        frm.set_intro("");
                    }, 5000);
                }
            })
            .catch(err => {
                frm.set_intro(
                    __("Items are filtered by the selected supplier. If no items appear, this supplier may not have any linked items."),
                    "blue"
                );
                // Auto-hide intro after 5 seconds
                setTimeout(() => {
                    frm.set_intro("");
                }, 5000);
            });
    } else if (is_tpin_functionality_enabled(frm)) {
        frm.set_intro(
            __("Select a supplier to filter items by supplier"),
            "orange"
        );
        // Auto-hide intro after 5 seconds
        setTimeout(() => {
            frm.set_intro("");
        }, 5000);
    } else {
        // Clear any existing intro when TPIN functionality is disabled
        frm.set_intro("");
    }
}

// ============================================================
// DEBUG FUNCTIONS (for testing)
// ============================================================

// Function to test item-supplier relationship (call from browser console)
window.test_item_supplier_relationship = function (supplier_name) {
    console.log("🔍 Testing item-supplier relationship for:", supplier_name);

    // Try to access Item Supplier table with permission handling
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Item Supplier",
            filters: {
                "supplier": supplier_name
            },
            fields: ["parent", "supplier", "supplier_part_no"],
            limit: 10
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                console.log("✅ Found", r.message.length, "items for supplier:", supplier_name);
                console.table(r.message);
            } else {
                console.log("❌ No items found for supplier:", supplier_name);
                console.log("💡 This supplier may not have any items linked in the Item Supplier table");
            }
        },
        error: function (err) {
            console.log("❌ Permission error accessing Item Supplier table:", err);
            console.log("💡 User may not have read permissions for Item Supplier doctype");
            console.log("💡 The system will automatically fall back to showing all items");
        }
    });
};

// Function to test our custom query (call from browser console)
window.test_custom_item_query = function (supplier_name, search_text = "") {
    console.log("🔍 Testing custom item query for supplier:", supplier_name, "search:", search_text);

    frappe.call({
        method: "ca_erpnext_zra.queries.item_supplier_query",
        args: {
            doctype: "Item",
            txt: search_text,
            searchfield: "name",
            start: 0,
            page_len: 20,
            filters: {
                supplier: supplier_name,
                is_sales_item: 1,
                is_purchase_item: 1,
                disabled: 0
            }
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                console.log("✅ Custom query returned", r.message.length, "items:");
                console.table(r.message);
            } else {
                console.log("❌ Custom query returned no items");
                console.log("💡 Check Error Log for detailed query information");
            }
        },
        error: function (err) {
            console.log("❌ Query failed with error:", err);
        }
    });
};

// Function to test direct SQL query (call from browser console)
window.test_direct_supplier_query = function (supplier_name) {
    console.log("🔍 Testing direct SQL query for supplier:", supplier_name);

    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Item",
            filters: [
                ["Item", "disabled", "=", 0],
                ["Item", "is_sales_item", "=", 1],
                ["Item", "is_purchase_item", "=", 1],
                ["Item Supplier", "supplier", "=", supplier_name]
            ],
            fields: ["name", "item_code", "item_name"],
            limit: 20
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                console.log("✅ Direct query returned", r.message.length, "items:");
                console.table(r.message);
            } else {
                console.log("❌ Direct query returned no items");
            }
        },
        error: function (err) {
            console.log("❌ Direct query failed:", err);
        }
    });
};

// Function to check what's actually in the Item Supplier table
window.check_item_supplier_table = function (item_name) {
    console.log("🔍 Checking Item Supplier table for item:", item_name);

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Item",
            name: item_name
        },
        callback: function (r) {
            if (r.message) {
                console.log("📋 Item details:");
                console.log("- Name:", r.message.name);
                console.log("- Item Code:", r.message.item_code);
                console.log("- Item Name:", r.message.item_name);
                console.log("- Disabled:", r.message.disabled);
                console.log("- Is Sales Item:", r.message.is_sales_item);
                console.log("- Is Purchase Item:", r.message.is_purchase_item);

                if (r.message.supplier_items && r.message.supplier_items.length > 0) {
                    console.log("✅ Supplier Items found:");
                    console.table(r.message.supplier_items);
                } else {
                    console.log("❌ No supplier items found in this item");
                }
            }
        },
        error: function (err) {
            console.log("❌ Failed to get item details:", err);
        }
    });
};

// Function to help link items to suppliers (call from browser console)
window.link_items_to_supplier = function (supplier_name, item_codes_array) {
    console.log("🔗 Linking items to supplier:", supplier_name);
    console.log("Items to link:", item_codes_array);

    if (!Array.isArray(item_codes_array) || item_codes_array.length === 0) {
        console.log("❌ Please provide an array of item codes");
        return;
    }

    item_codes_array.forEach(item_code => {
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Item",
                name: item_code
            },
            callback: function (r) {
                if (r.message) {
                    // Add supplier to item's supplier list
                    let item_doc = r.message;

                    // Check if supplier already exists
                    let existing_supplier = item_doc.supplier_items?.find(s => s.supplier === supplier_name);

                    if (!existing_supplier) {
                        if (!item_doc.supplier_items) {
                            item_doc.supplier_items = [];
                        }

                        item_doc.supplier_items.push({
                            supplier: supplier_name,
                            supplier_part_no: item_code
                        });

                        frappe.call({
                            method: "frappe.client.save",
                            args: {
                                doc: item_doc
                            },
                            callback: function (save_r) {
                                if (save_r.message) {
                                    console.log("✅ Linked", item_code, "to", supplier_name);
                                } else {
                                    console.log("❌ Failed to link", item_code, "to", supplier_name);
                                }
                            }
                        });
                    } else {
                        console.log("ℹ️ Item", item_code, "already linked to", supplier_name);
                    }
                }
            }
        });
    });
};