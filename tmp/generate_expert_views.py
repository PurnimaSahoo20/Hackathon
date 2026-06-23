import os
import re

file_path = r'd:\OKCL\Hackathon\code\Bput-Hackathon\features\views.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# We need to extract the jury views and duplicate them for expert.
# Let's find where send_jury_invite starts and where save_marking_parameter starts.
start_str = "def send_jury_invite(request):"
end_str = "def save_marking_parameter(request):"

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx != -1 and end_idx != -1:
    # Go back to the @login_required decorator
    real_start_idx = content.rfind("@login_required", 0, start_idx)
    real_end_idx = content.rfind("@login_required", 0, end_idx)
    
    jury_views_content = content[real_start_idx:real_end_idx]
    
    expert_views_content = jury_views_content.replace('jury', 'expert').replace('Jury', 'Expert')
    expert_views_content = expert_views_content.replace('juries', 'experts')
    expert_views_content = expert_views_content.replace('_send_expert_welcome_email', '_send_jury_welcome_email') # Keep the same welcome email or change it
    
    # Let's add them before save_marking_parameter
    new_content = content[:real_end_idx] + "\n# ── Expert Onboarding (Generated) ──\n\n" + expert_views_content + "\n" + content[real_end_idx:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Expert views generated successfully.")
else:
    print("Could not find jury views block.")
