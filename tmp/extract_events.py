import ast

with open('d:/OKCL/Hackathon/code/Bput-Hackathon/accounts/views.py', 'r', encoding='utf-8') as f:
    code = f.read()

tree = ast.parse(code)

events_funcs = [
    'create_hackathon', 'edit_hackathon', 'view_hackathon', 'delete_hackathon',
    'create_problem_statement', 'edit_problem_statement', 'delete_problem_statement', 'publish_problem_statement',
    'create_creative_material', 'delete_creative_material', 'suspend_creative_material'
]

lines_to_extract = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in events_funcs:
        start = node.lineno
        end = node.end_lineno
        lines_to_extract.append((start, end, node.name))

code_lines = code.splitlines()

output = []
for start, end, name in sorted(lines_to_extract):
    output.append('\n')
    output.append('\n'.join(code_lines[start-1:end]))

with open('d:/OKCL/Hackathon/code/Bput-Hackathon/events/views.py', 'w', encoding='utf-8') as fw:
    fw.write('''
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User, Role, SuperadminProfile, AdminProfile
from events.models import Hackathon, ProblemStatement, CreativeMaterial
from features.models import Team, Venue

def _superadmin_required(request):
    return (
        request.user.is_authenticated and
        (request.user.is_superuser or
         (request.user.role and request.user.role.name in ('Super Admin', 'Admin')))
    )

''' + '\n'.join(output))

print(f"Extracted {len(lines_to_extract)} functions.")
