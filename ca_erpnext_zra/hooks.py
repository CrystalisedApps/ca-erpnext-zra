app_name = "ca_erpnext_zra"
app_title = "CA ERPNext ZRA"
app_publisher = "Crystalised Apps"
app_description = "A Frappe custom app that integrates with ZRA VSDC API."
app_email = "support@crystalisedapps.com"
app_license = "agpl-3.0"





fixtures = [

]

doctype_js = {
    "Item": "public/js/item.js",
    "Sales Invoice": "public/js/sales_invoice.js"
}
# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "ca_erpnext_zra",
# 		"logo": "/assets/ca_erpnext_zra/logo.png",
# 		"title": "Ca Erpnext Zra",
# 		"route": "/ca_erpnext_zra",
# 		"has_permission": "ca_erpnext_zra.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/ca_erpnext_zra/css/ca_erpnext_zra.css"
# app_include_js = "/assets/ca_erpnext_zra/js/ca_erpnext_zra.js"

# include js, css files in header of web template
# web_include_css = "/assets/ca_erpnext_zra/css/ca_erpnext_zra.css"
# web_include_js = "/assets/ca_erpnext_zra/js/ca_erpnext_zra.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "ca_erpnext_zra/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "ca_erpnext_zra/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "ca_erpnext_zra.utils.jinja_methods",
# 	"filters": "ca_erpnext_zra.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "ca_erpnext_zra.install.before_install"
# after_install = "ca_erpnext_zra.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "ca_erpnext_zra.uninstall.before_uninstall"
# after_uninstall = "ca_erpnext_zra.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ca_erpnext_zra.utils.before_app_install"
# after_app_install = "ca_erpnext_zra.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ca_erpnext_zra.utils.before_app_uninstall"
# after_app_uninstall = "ca_erpnext_zra.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ca_erpnext_zra.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	# "*": {
	# 	"on_update": "method",
	# 	"on_cancel": "method",
	# 	"on_trash": "method"
	
    "Sales Invoice": {
        "before_save": ["ca_erpnext_zra.ca_erpnext_zra.overrides.server.shared_override.before_save"],
        "on_submit": [
            "ca_erpnext_zra.ca_erpnext_zra.overrides.server.sales_invoice_override.on_submit",
            "ca_erpnext_zra.ca_erpnext_zra.apis.stock_api.send_sales_to_zra"
        ],
    }
}
# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"ca_erpnext_zra.tasks.all"
# 	],
# 	"daily": [
# 		"ca_erpnext_zra.tasks.daily"
# 	],
# 	"hourly": [
# 		"ca_erpnext_zra.tasks.hourly"
# 	],
# 	"weekly": [
# 		"ca_erpnext_zra.tasks.weekly"
# 	],
# 	"monthly": [
# 		"ca_erpnext_zra.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "ca_erpnext_zra.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "ca_erpnext_zra.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "ca_erpnext_zra.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["ca_erpnext_zra.utils.before_request"]
# after_request = ["ca_erpnext_zra.utils.after_request"]

# Job Events
# ----------
# before_job = ["ca_erpnext_zra.utils.before_job"]
# after_job = ["ca_erpnext_zra.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"ca_erpnext_zra.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

