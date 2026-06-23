import json
import re

def main():
    log_path = r'C:\Users\purni\.gemini\antigravity-ide\brain\571974e5-fd1f-423e-8ba5-12a7015a79be\.system_generated\logs\transcript.jsonl'
    
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = list(f)
        
    data = json.loads(lines[8])
    content = data['content']
    extracted_lines = []
    
    for line in content.split('\n'):
        m = re.match(r'^(\d+):(.*)', line)
        if m:
            val = m.group(2)
            if val.startswith(' '):
                val = val[1:]
            extracted_lines.append(val)
            
    # Apply our fixes
    modified_lines = []
    for line in extracted_lines:
        # 1. Remove limit of 10 voice of inspiration assets
        if 'voice_inspiration_assets = voice_inspiration_assets[:10]' in line:
            print("Removing limit: voice_inspiration_assets = voice_inspiration_assets[:10]")
            # Skip this line
            continue
        # 2. Remove limit of leaders shown in template
        if "'leaders': leaders[:6]" in line:
            print("Removing limit: 'leaders': leaders[:6] -> 'leaders': leaders")
            line = line.replace("'leaders': leaders[:6]", "'leaders': leaders")
        modified_lines.append(line)
        
    # Read the first 580 lines from events/views.py (which is clean)
    with open('events/views.py', 'r', encoding='utf-8') as f:
        original_lines = f.readlines()
        
    prefix_lines = [line.rstrip('\r\n') for line in original_lines[:580]]
    
    # Combine them
    final_content = '\n'.join(prefix_lines + modified_lines)
    
    with open('events/views.py', 'w', encoding='utf-8') as f:
        f.write(final_content)
        
    print("Successfully restored and updated events/views.py!")

if __name__ == '__main__':
    main()
