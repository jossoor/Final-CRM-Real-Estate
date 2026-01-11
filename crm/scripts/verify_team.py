
import frappe

def execute():
    leader_email = "info@benchmarkarabia.com"
    team_name = frappe.db.exists("Team", {"team_leader": leader_email})
    if not team_name:
        print("Team not found!")
        return
    
    team = frappe.get_doc("Team", team_name)
    count = len(team.team_member)
    print(f"Team Leader: {team.team_leader}")
    print(f"Member Count: {count}")
    
    if count > 0:
        print("First 5 members:")
        for member in team.team_member[:5]:
            print(f"- {member.member}")
    else:
        print("No members found.")

if __name__ == "__main__":
    execute()
