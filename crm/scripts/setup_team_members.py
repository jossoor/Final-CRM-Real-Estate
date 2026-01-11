
import frappe

def execute():
    leader_email = "info@benchmarkarabia.com"
    frappe.flags.mute_emails = True
    
    # Check if user exists
    if not frappe.db.exists("User", leader_email):
        print(f"User {leader_email} does not exist. Creating...")
        user = frappe.new_doc("User")
        user.email = leader_email
        user.first_name = "Info"
        user.last_name = "Benchmark Arabia"
        user.enabled = 1
        user.send_welcome_email = 0
        user.save(ignore_permissions=True)
        print(f"Created user {leader_email}")
    else:
        print(f"User {leader_email} exists.")

    # Get or create Team
    team_name = frappe.db.exists("Team", {"team_leader": leader_email})
    if team_name:
        team = frappe.get_doc("Team", team_name)
        print(f"Using existing Team: {team.name}")
    else:
        team = frappe.new_doc("Team")
        team.team_leader = leader_email
        print(f"Creating new Team for leader: {leader_email}")

    # Get all enabled users excluding system users and the leader
    users = frappe.get_all("User", filters={
        "enabled": 1,
        "name": ["not in", ["Administrator", "Guest", leader_email]]
    }, fields=["name"])

    current_members = [row.member for row in team.team_member]
    
    added_count = 0
    for user in users:
        if user.name not in current_members:
            team.append("team_member", {
                "member": user.name
            })
            added_count += 1
            print(f"Adding {user.name} to team.")

    if added_count > 0:
        team.save()
        frappe.db.commit()
        print(f"Successfully added {added_count} members to the team.")
    else:
        print("No new members to add.")

if __name__ == "__main__":
    execute()
