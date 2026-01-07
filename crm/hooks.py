app_name = "crm"
app_title = "Jossoor CRM"
app_publisher = "Frappe Technologies Pvt. Ltd."
app_description = "Kick-ass Open Source CRM"
app_email = "shariq@frappe.io"
app_license = "AGPLv3"
app_icon_url = "/assets/crm/images/logo.svg"
app_icon_title = "CRM"
app_icon_route = "/crm"

# Apps
# ------------------

# required_apps = []
add_to_apps_screen = [
    {
        "name": "crm",
        "logo": "/assets/crm/images/logo.svg",
        "title": "CRM",
        "route": "/crm",
        "has_permission": "crm.api.check_app_permission",
    }
]

doctype_js = {
    "Reservation": "crm/fcrm/doctype/reservation/reservation.js"
}

# Includes in <head>
# ------------------

# app_include_css = "/assets/crm/css/crm.css"
# app_include_js = "/assets/crm/js/crm.js"

# web_include_css = "/assets/crm/css/crm.css"
# web_include_js = "/assets/crm/js/crm.js"

# hooks.py (snippet)
web_include_js = [
    "/assets/your_app/js/portal_leads_menu.js"
]
web_include_css = [
    "/assets/your_app/css/portal_leads_menu.css"
]

# website_theme_scss = "crm/public/scss/website"

# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# page_js = {"page" : "public/js/file.js"}

# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"CRM Lead" : "public/js/crm_lead_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# home_page = "login"

# role_home_page = {
#   "Role": "home_page"
# }

website_route_rules = [
    {"from_route": "/crm/<path:app_path>", "to_route": "crm"},
]

# Generators
# ----------

# website_generators = ["Web Page"]

# Jinja
# ----------

# jinja = {
#   "methods": "crm.utils.jinja_methods",
#   "filters": "crm.utils.jinja_filters"
# }

# Installation
# ------------

before_install = "crm.install.before_install"
after_install = "crm.install.after_install"

# Uninstallation
# ------------

before_uninstall = "crm.uninstall.before_uninstall"
# after_uninstall = "crm.uninstall.after_uninstall"

# Integration Setup
# ------------------
# before_app_install = "crm.utils.before_app_install"
# after_app_install = "crm.utils.after_app_install"

# Integration Cleanup
# -------------------
# before_app_uninstall = "crm.utils.before_app_uninstall"
# after_app_uninstall = "crm.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# notification_config = "crm.notifications.get_notification_config"

# Permissions
# -----------

permission_query_conditions = {
    "CRM Lead": "crm.fcrm.permissions.leads_permissions.get_permission_query_conditions",
    "ToDo": "crm.fcrm.permissions.leads_permissions.get_permission_query_conditions",
}

has_permission = {
    "CRM Lead": "crm.fcrm.permissions.leads_permissions.has_permission",
    "ToDo": "crm.fcrm.permissions.leads_permissions.has_permission",
}

# DocType Class
# ---------------
override_doctype_class = {
    "Contact": "crm.overrides.contact.CustomContact",
    "Email Template": "crm.overrides.email_template.CustomEmailTemplate",
}

# Document Events
# ---------------
doc_events = {
    "Contact": {
        "validate": ["crm.api.contact.validate"],
    },
    "ToDo": {
        "after_insert": ["crm.api.todo.after_insert"],
        "on_update": ["crm.api.todo.on_update"],
        # "before_insert": ["crm.permissions.assign_to.validate_todo_assignment"],
    },
    # عند تحديث تعليق موجود (موجودة بالفعل)
    "Comment": {
        "on_update": ["crm.api.comment.on_update"],
        # جديد: بعد إضافة تعليق جديد، أعد حساب Delayed بناءً على آخر Reminder متأخر
        "after_insert": ["crm.api.reminders.recalc_from_comment"],
    },
    "WhatsApp Message": {
        "validate": ["crm.api.whatsapp.validate"],
        "on_update": ["crm.api.whatsapp.on_update"],
    },
    "CRM Deal": {
        "on_update": [
            "crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.create_customer_in_erpnext"
        ],
    },
    "User": {
        "before_validate": ["crm.api.demo.validate_user"],
        "validate_reset_password": ["crm.api.demo.validate_reset_password"],
    },
    "CRM Lead": {
        "before_insert": ["crm.duplicate_lead.check_duplicates"],
        "after_insert": ["crm.duplicate_lead.append_to_original_lead"],
    },
    # بثّ الريـال-تايم للجرس عند إنشاء Notification Log
    "Notification Log": {

          "after_insert": [
            "crm.api.notifications.broadcast_log_realtime",
            "crm.api.firebase.send_push_for_notification_log",
        ]


    },
    # جديد: أي تغيير في الـ Reminder يعيد حساب Delayed لأحدث تعليق على نفس المستند
    "Reminder": {
        "after_insert": ["crm.api.reminders.recalc_from_reminder"],
        "on_update": ["crm.api.reminders.recalc_from_reminder"],
        "on_trash": ["crm.api.reminders.recalc_from_reminder"],
    },
    # التحقق من due_date وتحديث الحالة إلى Backlog تلقائياً
    "CRM Task": {
        "on_load": ["crm.api.task_status.check_and_update_task_status"],
        "on_update": ["crm.api.task_status.check_and_update_task_status"],
    },

}



# Scheduled Tasks
# ---------------
# تشغيل الريمايندر كل دقيقة (runner داخلي بدون تعديل Core)
scheduler_events = {
    "cron": {
        "*/1 * * * *": [
            "crm.reminder_runner.run_reminders_locked",
            "crm.api.task_status.update_overdue_tasks"  # تحديث المهام المتأخرة كل دقيقة
        ]
    }
}

# Testing
# -------
# before_tests = "crm.install.before_tests"

# Patches
# -------
patches = [
    "crm.patches.v1_0.ensure_mobile_oauth_and_tokens",
    "crm.patches.v1_0.add_late_status_to_crm_task",
    # "crm.patches.v1_0.set_refresh_token_expiry_1_hour",  # Disabled - using default Frappe behavior (infinite refresh tokens)
]

# Overriding Methods
# ------------------------------
#
#override_whitelisted_methods = {
   #"frappe.desk.doctype.event.event.get_events": "crm.event.get_events"

 #}
# Overriding Methods
# ------------------------------



#
# override_doctype_dashboards = {
#   "Task": "crm.task.get_dashboard_data"
# }

# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore these doctypes when checking for linked documents before delete
# This allows deleting CRM Lead and CRM Task even if they have linked notifications, todos, etc.
ignore_links_on_delete = [
	"Communication", 
	"ToDo", 
	"Notification Log", 
	"CRM Notification", 
	"Comment", 
	"DocShare"
]

# Request Events
# --------------
# before_request = ["crm.oauth_fix.ensure_oauth_fix_applied"]  # Disabled - using default Frappe OAuth behavior
# after_request  = ["crm.utils.after_request"]

# Job Events
# ----------
# before_job = ["crm.utils.before_job"]
# after_job  = ["crm.utils.after_job"]

# User Data Protection
# --------------------
# user_data_fields = [
#   {...},
# ]

# Authentication and authorization
# --------------------------------
# auth_hooks = ["crm.auth.validate"]

after_migrate = ["crm.fcrm.doctype.fcrm_settings.fcrm_settings.after_migrate"]

# OAuth Fix - Disabled - using default Frappe behavior (infinite refresh tokens)
# boot_session = ["crm.oauth_fix.ensure_oauth_fix_applied"]  # Disabled - using default Frappe OAuth behavior

standard_dropdown_items = [
    {
        "name1": "app_selector",
        "label": "Apps",
        "type": "Route",
        "route": "#",
        "is_standard": 1,
    },
    {
        "name1": "toggle_theme",
        "label": "Toggle theme",
        "type": "Route",
        "icon": "moon",
        "route": "#",
        "is_standard": 1,
    },
    {
        "name1": "settings",
        "label": "Settings",
        "type": "Route",
        "icon": "settings",
        "route": "#",
        "is_standard": 1,
    },
    {
        "name1": "login_to_fc",
        "label": "Login to Frappe Cloud",
        "type": "Route",
        "route": "#",
        "is_standard": 1,
    },
    {
        "name1": "about",
        "label": "About",
        "type": "Route",
        "icon": "info",
        "route": "#",
        "is_standard": 1,
    },
    {
        "name1": "separator",
        "label": "",
        "type": "Separator",
        "is_standard": 1,
    },
    {
        "name1": "logout",
        "label": "Log out",
        "type": "Route",
        "icon": "log-out",
        "route": "#",
        "is_standard": 1,
    },
]

fixtures = [
    "Client Script",
    
    {
        "dt": "Client Script",
        "filters": [["name", "in", ["Filtered Buttons", "Highlight Orginal lead has Duplicates"]]],
    },
    {"dt": "Server Script", "filters": [["name", "in", ["Hot Leads", "FCRM Note For Hot Leads", "ToDo For Hot Leads"]]]},
    {"dt": "DocType", "filters": [["name", "in", ["Saved Filter"]]]},
    {"dt": "DocType", "filters": [["name", "in", ["CRM Lead"," CRM Lead Status","CRM Task","CRM Communication Status","Comment"]]]},


  


]
