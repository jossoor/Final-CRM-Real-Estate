
import frappe

def execute(names=None):
    frappe.flags.ignore_permissions = True
    filters = {}
    if names:
        filters["name"] = ["in", names]
        
    leads = frappe.get_all("CRM Lead", filters=filters, fields=["name", "lead_owner"])
    count = 0
    total = len(leads)
    
    print(f"Found {total} leads to process...")
    
    for lead_data in leads:
        if not lead_data.lead_owner:
            continue
            
        try:
            doc = frappe.get_doc("CRM Lead", lead_data.name)
            doc.share_with_agent(doc.lead_owner)
            count += 1
            if count % 100 == 0:
                frappe.db.commit()
                print(f"Processed {count}/{total} leads...")
        except Exception as e:
            print(f"Error processing {lead_data.name}: {e}")

    frappe.db.commit()
    print(f"Completed! Processed {count} leads.")

if __name__ == "__main__":
    execute()
