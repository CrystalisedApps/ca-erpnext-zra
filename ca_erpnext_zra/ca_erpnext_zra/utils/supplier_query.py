import frappe

@frappe.whitelist()
def supplier_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom query for supplier search in Crystallised ZRA Smart Purchases
    """
    return frappe.db.sql("""
        SELECT name, supplier_name, tax_id
        FROM `tabSupplier`
        WHERE disabled = 0
        AND (name LIKE %(txt)s 
            OR supplier_name LIKE %(txt)s 
            OR tax_id LIKE %(txt)s)
        ORDER BY supplier_name
        LIMIT %(page_len)s OFFSET %(start)s
    """, {
        'txt': '%' + txt + '%',
        'start': start,
        'page_len': page_len
    })

    