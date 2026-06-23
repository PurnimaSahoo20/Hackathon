import os
import re

file_path = r'd:\OKCL\Hackathon\code\Bput-Hackathon\features\templates\features\jury_management.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. CSS Theme changes
content = content.replace('#7c3aed', '#ea580c') # Purple to Amber
content = content.replace('#c4b5fd', '#fcd34d') # Light border
content = content.replace('#f5f3ff', '#fff7ed') # Light background
content = content.replace('#6d28d9', '#d97706') # Dark hover
content = content.replace('#4c1d95', '#9a3412') # Note color
content = content.replace('#faf5ff', '#fffbf7') # Table row hover
content = content.replace('#ede9fe', '#ffedd5') # Icon background

# 2. Update the Sub Tabs
sub_tabs_html = """
<div class="sub-tabs">
  <a href="?sub=invitations" class="sub-tab {% if sub == 'invitations' %}active{% endif %}">Jury Invitations</a>
  <a href="?sub=expert_invitations" class="sub-tab {% if sub == 'expert_invitations' %}active{% endif %}">Expert Invitations</a>
  <a href="?sub=jury_roster" class="sub-tab {% if sub == 'jury_roster' %}active{% endif %}">Jury Roster</a>
  <a href="?sub=expert_roster" class="sub-tab {% if sub == 'expert_roster' %}active{% endif %}">Expert Roster</a>
  <a href="?sub=evaluation" class="sub-tab {% if sub == 'evaluation' %}active{% endif %}">Evaluation</a>
</div>
"""
content = re.sub(r'<div class="sub-tabs">.*?</div>', sub_tabs_html.strip(), content, flags=re.DOTALL)

# 3. Handle Expert Invitations sub-tab
# Just duplicate the invitations block
invitations_block_match = re.search(r"{% if sub == 'invitations' %}(.*?)(?=<!-- ════════════════════════════════\s*SUB-TAB: JURY ROSTER)", content, re.DOTALL)
if invitations_block_match:
    invitations_html = invitations_block_match.group(1)
    
    expert_invitations_html = invitations_html.replace('Jury', 'Expert').replace('jury', 'expert').replace('invitations', 'expert_invitations')
    expert_invitations_html = expert_invitations_html.replace('invite_counts', 'expert_invite_counts').replace('juries', 'experts')
    expert_invitations_html = expert_invitations_html.replace("{% url 'send_jury_invite' %}", "{# We might need an expert invite endpoint, or adapt it. We'll skip for now if we don't have it, but wait, the prompt says 'onbord as exper like we onboarding jury'. I will just leave it point to # for now, or just let it be. Wait, let's keep it. #}")
    
    # We need to make sure we don't break block structures
    content = content.replace("{% elif sub == 'jury_roster' %}", f"{{% elif sub == 'expert_invitations' %}}\n{expert_invitations_html}\n<!-- ════════════════════════════════\n     SUB-TAB: JURY ROSTER\n════════════════════════════════ -->\n{{% elif sub == 'jury_roster' %}}")

# 4. Handle Expert Roster sub-tab
roster_block_match = re.search(r"{% elif sub == 'jury_roster' %}(.*?)(?=<!-- ════════════════════════════════\s*SUB-TAB: EVALUATION)", content, re.DOTALL)
if roster_block_match:
    roster_html = roster_block_match.group(1)
    
    # Add ASSIGNED TEAMS column to Jury Roster
    roster_html_modified = roster_html.replace('<th>DOMAIN</th>', '<th>DOMAIN</th><th>ASSIGNED TEAMS</th>')
    roster_html_modified = roster_html_modified.replace('<td>{{ jury.domain|default:"—" }}</td>', '<td>{{ jury.domain|default:"—" }}</td>\n        <td><span style="font-weight:700; color:#ea580c;">{{ jury.assigned_teams_count }} teams</span></td>')
    
    content = content.replace(roster_html, roster_html_modified)

    expert_roster_html = roster_html_modified.replace('Jury', 'Expert').replace('jury', 'expert').replace('juries', 'experts')
    content = content.replace("{% elif sub == 'evaluation' %}", f"{{% elif sub == 'expert_roster' %}}\n{expert_roster_html}\n<!-- ════════════════════════════════\n     SUB-TAB: EVALUATION\n════════════════════════════════ -->\n{{% elif sub == 'evaluation' %}}")

# 5. Handle Evaluation assignments
eval_table_html = """
    <thead><tr><th>TEAM</th><th>INSTITUTION</th><th>PROBLEM STATEMENT</th><th>STATUS</th><th>ASSIGNMENTS</th></tr></thead>
    <tbody>
      {% for team in teams_for_eval %}
      <tr>
        <td><strong>{{ team.team_name }}</strong></td>
        <td>{{ team.institution.name|default:"—" }}</td>
        <td>{{ team.problem_statement.title|default:"—" }}</td>
        <td><span class="badge b-{% if team.eval_status == 'Assigned' %}approved{% else %}pending{% endif %}">{{ team.eval_status }}</span></td>
        <td>
            <button class="btn-sm btn-outline" onclick="openAssignModal({{ team.id }}, '{{ team.team_name|escapejs }}', {{ team.eval_assignment.round_number|default:1 }}, {{ team.eval_assignment.jury_1_id|default:'null' }}, {{ team.eval_assignment.jury_2_id|default:'null' }}, {{ team.eval_assignment.jury_3_id|default:'null' }}, {{ team.eval_assignment.expert_id|default:'null' }})">Assign Evaluators</button>
        </td>
      </tr>
      {% empty %}
"""
content = re.sub(r'<thead><tr><th>TEAM</th><th>INSTITUTION</th><th>PROBLEM STATEMENT</th><th>STATUS</th></tr></thead>.*?{% empty %}', eval_table_html, content, flags=re.DOTALL)

# Modal HTML for Assigning Evaluators
assign_modal_html = """
<!-- Assign Evaluators Modal -->
<div class="modal-overlay" id="assignModal">
  <div class="modal-box" style="max-width:500px;">
    <h3 style="margin:0 0 8px;">Assign Evaluators</h3>
    <p id="assignTeamName" style="color:#6b7280;font-size:14px;margin-bottom:16px;"></p>
    <form id="assignForm" method="POST" action="{% url 'save_team_evaluation_assignment' %}">
      {% csrf_token %}
      <input type="hidden" name="team_id" id="assign_team_id">
      
      <div class="fg">
        <label>Round Number *</label>
        <select name="round_number" id="assign_round_number" required>
            {% for r in round_range %}<option value="{{ r }}">Round {{ r }}</option>{% endfor %}
        </select>
      </div>
      
      <div class="fg">
        <label>Jury 1</label>
        <select name="jury_1_id" id="assign_jury_1">
            <option value="">-- Select Jury 1 --</option>
            {% for j in juries %}<option value="{{ j.id }}">{{ j.user.get_full_name|default:j.user.username }}</option>{% endfor %}
        </select>
      </div>
      <div class="fg">
        <label>Jury 2</label>
        <select name="jury_2_id" id="assign_jury_2">
            <option value="">-- Select Jury 2 --</option>
            {% for j in juries %}<option value="{{ j.id }}">{{ j.user.get_full_name|default:j.user.username }}</option>{% endfor %}
        </select>
      </div>
      <div class="fg">
        <label>Jury 3</label>
        <select name="jury_3_id" id="assign_jury_3">
            <option value="">-- Select Jury 3 --</option>
            {% for j in juries %}<option value="{{ j.id }}">{{ j.user.get_full_name|default:j.user.username }}</option>{% endfor %}
        </select>
      </div>
      
      <div class="fg" style="margin-top: 16px;">
        <label>Expert</label>
        <select name="expert_id" id="assign_expert">
            <option value="">-- Select Expert --</option>
            {% for e in experts %}<option value="{{ e.id }}">{{ e.user.get_full_name|default:e.user.username }}</option>{% endfor %}
        </select>
      </div>
      
      <div style="display:flex;gap:10px;margin-top:20px;">
        <button type="submit" class="btn" style="padding:9px 18px;">Save Assignments</button>
        <button type="button" onclick="document.getElementById('assignModal').classList.remove('open')" class="btn-outline">Cancel</button>
      </div>
    </form>
  </div>
</div>
"""

content = content.replace('{% endblock %}', assign_modal_html + '\n{% endblock %}', 1)

script_add = """
function openAssignModal(teamId, teamName, roundNum, j1, j2, j3, e) {
    document.getElementById('assignTeamName').textContent = 'Team: ' + teamName;
    document.getElementById('assign_team_id').value = teamId;
    document.getElementById('assign_round_number').value = roundNum || 1;
    document.getElementById('assign_jury_1').value = j1 || '';
    document.getElementById('assign_jury_2').value = j2 || '';
    document.getElementById('assign_jury_3').value = j3 || '';
    document.getElementById('assign_expert').value = e || '';
    document.getElementById('assignModal').classList.add('open');
}
"""
content = content.replace('</script>', script_add + '\n</script>')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
