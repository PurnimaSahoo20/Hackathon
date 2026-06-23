import ast

with open('d:/OKCL/Hackathon/code/Bput-Hackathon/accounts/views.py', 'r', encoding='utf-8') as f:
    code = f.read()

tree = ast.parse(code)
events_funcs = [
    'create_hackathon', 'edit_hackathon', 'view_hackathon', 'delete_hackathon',
    'create_problem_statement', 'edit_problem_statement', 'delete_problem_statement', 'publish_problem_statement',
    'create_creative_material', 'delete_creative_material', 'suspend_creative_material'
]

lines_to_remove = set()
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in events_funcs:
        for i in range(node.lineno - 1, node.end_lineno):
            lines_to_remove.add(i)
        
        # also remove any decorators that precede it
        if getattr(node, 'decorator_list', None):
            for dec in node.decorator_list:
                for i in range(dec.lineno - 1, dec.end_lineno):
                    lines_to_remove.add(i)

code_lines = code.splitlines()
new_lines = []
for i, line in enumerate(code_lines):
    if i not in lines_to_remove:
        new_lines.append(line)

with open('d:/OKCL/Hackathon/code/Bput-Hackathon/accounts/views.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f"Removed {len(lines_to_remove)} lines from accounts/views.py")
