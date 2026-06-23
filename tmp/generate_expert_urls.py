import os

file_path = r'd:\OKCL\Hackathon\code\Bput-Hackathon\features\urls.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract jury URLs
start_str = "# ── Jury Onboarding (invitation flow) ──"
end_str = "# ── Evaluation parameters ──"

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx != -1 and end_idx != -1:
    jury_urls = content[start_idx:end_idx]
    
    expert_urls = jury_urls.replace('jury', 'expert').replace('Jury', 'Expert')
    
    new_content = content[:end_idx] + "\n# ── Expert Onboarding (invitation flow) ──\n" + expert_urls + "\n" + content[end_idx:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Expert URLs generated successfully.")
else:
    print("Could not find jury URLs block.")
