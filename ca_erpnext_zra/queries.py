import frappe

@frappe.whitelist()
def supplier_tpin_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom query for supplier TPIN field to show TPIN alongside supplier name
    Returns supplier name as value but displays "TPIN - Supplier Name" as label
    Only shows suppliers that have tax_id (TPIN) values
    """
    try:
        conditions = []
        values = {'txt': f'%{txt}%', 'start': start, 'page_len': page_len}
        
        # Add filter conditions if provided
        if filters:
            for key, value in filters.items():
                if key == 'disabled':
                    conditions.append("disabled = %(disabled)s")
                    values['disabled'] = value
        
        # Default condition for disabled
        if 'disabled' not in conditions:
            conditions.append("disabled = 0")
        
        # IMPORTANT: Only show suppliers that have tax_id (TPIN)
        conditions.append("tax_id IS NOT NULL")
        conditions.append("tax_id != ''")
        conditions.append("TRIM(tax_id) != ''")
        
        # Build the WHERE clause
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT 
                name as value,
                CONCAT(tax_id, ' - ', supplier_name) as label
            FROM `tabSupplier`
            WHERE 
                {where_clause}
                AND (
                    supplier_name LIKE %(txt)s
                    OR tax_id LIKE %(txt)s
                    OR name LIKE %(txt)s
                )
            ORDER BY 
                supplier_name
            LIMIT %(start)s, %(page_len)s
        """
        
        result = frappe.db.sql(query, values)
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in supplier_tpin_query: {str(e)}", "Supplier TPIN Query Error")
        # Return empty result on error
        return []

@frappe.whitelist()
def item_supplier_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom query for item filtering by supplier
    Shows only items that have the specified supplier in their Supplier Items child table
    """
    try:
        # Convert string parameters to proper types
        start = int(start) if start else 0
        page_len = int(page_len) if page_len else 20
        
        # Handle filters - can be string (JSON) or dict
        if isinstance(filters, str):
            import json
            try:
                filters = json.loads(filters)
            except:
                filters = {}
        elif not filters:
            filters = {}
        
        # Get the supplier filter
        supplier = filters.get('supplier') if filters else None
        
        if not supplier:
            # No supplier filter, return all items with standard filters
            return frappe.db.sql("""
                SELECT 
                    name,
                    item_code,
                    item_name
                FROM `tabItem`
                WHERE 
                    disabled = 0
                    AND is_sales_item = 1
                    AND is_purchase_item = 1
                    AND (
                        item_code LIKE %s
                        OR item_name LIKE %s
                    )
                ORDER BY 
                    item_code
                LIMIT %s, %s
            """, (f'%{txt}%', f'%{txt}%', start, page_len), as_dict=False)
        
        # frappe.log_error(f"Filtering items for supplier: {supplier}", "Item Supplier Query")
        
        # Query items that have this supplier in their Supplier Items child table
        # The child table is named "Item Supplier" and has parenttype "Item"
        query = """
            SELECT DISTINCT
                i.name,
                i.item_code,
                i.item_name
            FROM `tabItem` i
            WHERE 
                i.disabled = 0
                AND i.is_sales_item = 1
                AND i.is_purchase_item = 1
                AND EXISTS (
                    SELECT 1 
                    FROM `tabItem Supplier` isup 
                    WHERE isup.parent = i.name 
                    AND isup.parenttype = 'Item'
                    AND isup.supplier = %s
                )
                AND (
                    i.item_code LIKE %s
                    OR i.item_name LIKE %s
                )
            ORDER BY 
                i.item_code
            LIMIT %s, %s
        """
        
        search_txt = f'%{txt}%'
        params = (supplier, search_txt, search_txt, start, page_len)
        
        result = frappe.db.sql(query, params, as_dict=False)
        
        frappe.log_error(f"Query returned {len(result)} items for supplier {supplier}", "Item Supplier Query Result")
        
        if not result and txt:
            # No items found with search criteria, try without search filter
            query_no_search = """
                SELECT DISTINCT
                    i.name,
                    i.item_code,
                    i.item_name
                FROM `tabItem` i
                WHERE 
                    i.disabled = 0
                    AND i.is_sales_item = 1
                    AND i.is_purchase_item = 1
                    AND EXISTS (
                        SELECT 1 
                        FROM `tabItem Supplier` isup 
                        WHERE isup.parent = i.name 
                        AND isup.parenttype = 'Item'
                        AND isup.supplier = %s
                    )
                ORDER BY 
                    i.item_code
                LIMIT %s, %s
            """
            
            result = frappe.db.sql(query_no_search, (supplier, start, page_len), as_dict=False)
            frappe.log_error(f"Query without search returned {len(result)} items for supplier {supplier}", "Item Supplier Query No Search")
        
        if not result:
            # Still no results, fall back to all items
            frappe.log_error(f"No items found for supplier {supplier}, falling back to all items", "Item Supplier Fallback")
            return frappe.db.sql("""
                SELECT 
                    name,
                    item_code,
                    item_name
                FROM `tabItem`
                WHERE 
                    disabled = 0
                    AND is_sales_item = 1
                    AND is_purchase_item = 1
                    AND (
                        item_code LIKE %s
                        OR item_name LIKE %s
                    )
                ORDER BY 
                    item_code
                LIMIT %s, %s
            """, (f'%{txt}%', f'%{txt}%', start, page_len), as_dict=False)
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in item_supplier_query: {str(e)}", "Item Supplier Query Error")
        # Fallback to all items on any error
        try:
            start = int(start) if start else 0
            page_len = int(page_len) if page_len else 20
            return frappe.db.sql("""
                SELECT 
                    name,
                    item_code,
                    item_name
                FROM `tabItem`
                WHERE 
                    disabled = 0
                    AND is_sales_item = 1
                    AND is_purchase_item = 1
                    AND (
                        item_code LIKE %s
                        OR item_name LIKE %s
                    )
                ORDER BY 
                    item_code
                LIMIT %s, %s
            """, (f'%{txt}%', f'%{txt}%', start, page_len), as_dict=False)
        except:
            return []