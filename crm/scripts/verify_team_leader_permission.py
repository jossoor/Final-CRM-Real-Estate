
import frappe
from frappe.utils import random_string

def create_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    
    user = frappe.new_doc("User")
    user.email = email
    user.first_name = first_name
    user.enabled = 1
    user.send_welcome_email = 0
    user.insert(ignore_permissions=True)
    return user

def execute():
    frappe.flags.mute_emails = True
    # 1. Setup Users
    leader_email = f"leader_{random_string(5)}@example.com"
    member_email = f"member_{random_string(5)}@example.com"
    
    leader = create_user(leader_email, "Test Leader")
    member = create_user(member_email, "Test Member")
    
    print(f"Created Leader: {leader.name}")
    print(f"Created Member: {member.name}")

    # 2. Setup Team
    if not frappe.db.exists("Team", {"team_leader": leader.name}):
        team = frappe.new_doc("Team")
        team.team_leader = leader.name
        team.append("team_member", {"member": member.name})
        team.insert(ignore_permissions=True)
        print(f"Created Team: {team.name}")
    else:
        print("Team already exists (unexpected for random user)")

    # 3. Create Lead as Member
    # We simulate this by creating a lead and setting owner/lead_owner
    # Run as Administrator to avoid permission issues during creation/assignment
    # frappe.set_user(member.name) 
    lead = frappe.new_doc("CRM Lead")
    lead.first_name = f"Lead {random_string(5)}"
    lead.mobile_no = "+1234567890"
    lead.lead_owner = member.name 
    lead.insert(ignore_permissions=True)
    print(f"Created Lead: {lead.name} owned by {lead.lead_owner}")
    
    # 4. Verify Share
    frappe.set_user("Administrator")
    is_shared = frappe.db.exists("DocShare", {
        "share_name": lead.name,
        "share_doctype": "CRM Lead",
        "user": leader.name
    })
    
    if is_shared:
        print("SUCCESS: Lead is shared with Team Leader.")
    else:
        print("FAILURE: Lead is NOT shared with Team Leader.")

    # 5. Check Permission (Simulated)
    # Switch to Leader
    frappe.set_user(leader.name)
    has_perm = frappe.has_permission("CRM Lead", "read", doc=lead)
    print(f"Team Leader Read Permission: {has_perm}")
    
    if has_perm:
        print("SUCCESS: Team Leader has read permission.")
    else:
        print("FAILURE: Team Leader does NOT have read permission.")

    # Clean up
    frappe.set_user("Administrator")
    # frappe.delete_doc("CRM Lead", lead.name)
    # frappe.delete_doc("Team", team.name)
    # frappe.delete_doc("User", leader.name)
    # frappe.delete_doc("User", member.name)

if __name__ == "__main__":
    execute()
