import frappe
from frappe.utils import random_string

def verify():
    # Reload Doctype to ensure new field is available
    frappe.reload_doc("fcrm", "doctype", "CRM Lead")

    # 1. Create a Lead
    lead_email = f"test_lead_{random_string(5)}@example.com"
    lead = frappe.get_doc({
        "doctype": "CRM Lead",
        "first_name": "Test",
        "last_name": "Lead",
        "email": lead_email,
        "mobile_no": "+201000000000",
        "status": "New"
    }).insert(ignore_permissions=True)
    
    print(f"Created Lead: {lead.name}")

    # 2. Add a Comment
    comment_content = "This is a <b>bold</b> test comment."
    comment = frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": "CRM Lead",
        "reference_name": lead.name,
        "content": comment_content
    }).insert(ignore_permissions=True)
    
    # Trigger on_update manualy just in case (though insert should trigger it via hooks if configured)
    # Hooks usually run on insert/update. Let's check hooks.py configuration.
    # checking hooks.py: "Comment": { "on_update": ["crm.api.comment.on_update"], ... }
    # So we need to trigger on_update or save triggering on_update.
    comment.save()

    print(f"Added Comment: {comment.name}")

    # 3. Reload Lead and Check last_comment
    lead.reload()
    print(f"Lead last_comment: '{lead.last_comment}'")

    expected_comment = "This is a bold test comment."
    if lead.last_comment == expected_comment:
        print("SUCCESS: last_comment updated correctly!")
    else:
        print(f"FAILURE: Expected '{expected_comment}', got '{lead.last_comment}'")

if __name__ == "__main__":
    verify()
