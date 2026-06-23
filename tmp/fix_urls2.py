import os
import glob

html_files = glob.glob('d:/OKCL/Hackathon/code/Bput-Hackathon/**/*.html', recursive=True)

replace_map = {
    '"/accounts/create-hackathon/': '"/events/create-hackathon/',
    '"/accounts/edit-hackathon/': '"/events/edit-hackathon/',
    '"/accounts/view-hackathon/': '"/events/view-hackathon/',
    '"/accounts/delete-hackathon/': '"/events/delete-hackathon/',
    
    '"/accounts/create-problem-statement/': '"/events/create-problem-statement/',
    '"/accounts/edit-problem-statement/': '"/events/edit-problem-statement/',
    '"/accounts/delete-problem-statement/': '"/events/delete-problem-statement/',
    '"/accounts/publish-problem-statement/': '"/events/publish-problem-statement/',
    
    '"/accounts/create-creative/': '"/events/create-creative/',
    '"/accounts/delete-creative/': '"/events/delete-creative/',
    '"/accounts/suspend-creative/': '"/events/suspend-creative/',
    
    # Also fix single quotes instances just in case (JS actions mainly)
    "'/accounts/create-hackathon/": "'/events/create-hackathon/",
    "'/accounts/edit-hackathon/": "'/events/edit-hackathon/",
    "'/accounts/view-hackathon/": "'/events/view-hackathon/",
    "'/accounts/delete-hackathon/": "'/events/delete-hackathon/",
    
    "'/accounts/create-problem-statement/": "'/events/create-problem-statement/",
    "'/accounts/edit-problem-statement/": "'/events/edit-problem-statement/",
    "'/accounts/delete-problem-statement/": "'/events/delete-problem-statement/",
    "'/accounts/publish-problem-statement/": "'/events/publish-problem-statement/",
    
    "'/accounts/create-creative/": "'/events/create-creative/",
    "'/accounts/delete-creative/": "'/events/delete-creative/",
    "'/accounts/suspend-creative/": "'/events/suspend-creative/",
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
