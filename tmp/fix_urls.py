import os
import glob

html_files = glob.glob('d:/OKCL/Hackathon/code/Bput-Hackathon/**/*.html', recursive=True)

replace_map = {
    '"/accounts/features/': '"/features/',
    "'/accounts/features/": "'/features/"
}

updated_files = 0
for filepath in html_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = content
        for old_str, new_str in replace_map.items():
            new_content = new_content.replace(old_str, new_str)
            
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            updated_files += 1
            print("Updated", filepath)
    except Exception as e:
        print("Error on", filepath, e)

print(f"Total HTML files updated: {updated_files}")
