import re

log_path = 'C:/Users/purni/.gemini/antigravity/brain/b65bee06-ecbf-4d84-b723-954842e4c443/.system_generated/logs/overview.txt'
try:
    with open(log_path, 'r', encoding='utf-8') as f:
        data = f.read()
    
    # We want the last full HTML document that contains 'exec_mgt'
    matches = []
    # This regex is memory intensive, so let's use string operations
    for start in [m.start() for m in re.finditer(r'<!DOCTYPE html>', data)]:
        end = data.find('</html>', start)
        if end != -1:
            html = data[start:end+7]
            if "exec_mgt" in html and "admin_mgt" in html and "events" in html:
                matches.append(html)
    
    with open('tmp/restored.html', 'w', encoding='utf-8') as f:
        f.write(matches[-1] if matches else 'none')
    print(f"Found {len(matches)} matches. Written to tmp/restored.html")
except Exception as e:
    print(e)
