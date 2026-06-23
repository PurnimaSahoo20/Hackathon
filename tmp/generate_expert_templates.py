import os

templates_dir = r'd:\OKCL\Hackathon\code\Bput-Hackathon\features\templates\features'
templates_to_copy = [
    'jury_register_form.html',
    'jury_register_success.html',
    'jury_register_invalid.html',
    'jury_invitation_detail.html',
    'jury_invitation_edit.html',
    'jury_member_detail.html',
    'jury_member_edit.html'
]

for tmpl in templates_to_copy:
    src_path = os.path.join(templates_dir, tmpl)
    dst_path = os.path.join(templates_dir, tmpl.replace('jury', 'expert'))
    
    if os.path.exists(src_path):
        with open(src_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Replace occurrences of jury with expert
        new_content = content.replace('jury', 'expert')
        new_content = new_content.replace('Jury', 'Expert')
        new_content = new_content.replace('JURY', 'EXPERT')
        
        with open(dst_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Generated {dst_path}")
    else:
        print(f"File not found: {src_path}")
