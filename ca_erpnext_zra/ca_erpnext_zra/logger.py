"""Smart Logger initialisation"""

import frappe
from frappe.utils import logger

logger.set_log_level("DEBUG")
smart_logger = frappe.logger("smart", allow_site=True, file_count=50)
