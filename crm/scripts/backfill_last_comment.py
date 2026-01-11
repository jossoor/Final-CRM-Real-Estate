import frappe
from frappe.utils import strip_html

def backfill():
    leads = frappe.get_all("CRM Lead", fields=["name"])
    print(f"Found {len(leads)} leads. Starting backfill...")
    
    count = 0
    for lead_data in leads:
        lead_name = lead_data.name
        
        # Get latest comment
        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "CRM Lead",
                "reference_name": lead_name,
                "comment_type": "Comment"
            },
            fields=["content"],
            order_by="creation desc",
            limit=1
        )
        
        if comments:
            content = comments[0].content
            if content:
                clean_content = strip_html(content)
                if len(clean_content) > 140:
                    clean_content = clean_content[:137] + "..."
                
                frappe.db.set_value("CRM Lead", lead_name, "last_comment", clean_content)
                count += 1
                if count % 100 == 0:
                    print(f"Processed {count} leads...")
    
    print(f"Backfill complete. Updated {count} leads.")
    frappe.db.commit()

if __name__ == "__main__":
    backfill()
