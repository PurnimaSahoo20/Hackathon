import os

template_content = """{% extends 'base.html' %}
{% block title %}Jury & Evaluation Management — HackNexus{% endblock %}

{% block extra_css %}
<style>
  .sub-tabs{display:flex;gap:8px;background:#f3f4f6;padding:5px;border-radius:12px;margin-bottom:24px;width:fit-content;flex-wrap:wrap;}
  .sub-tab{padding:9px 22px;border-radius:9px;font-weight:700;font-size:14px;text-decoration:none;color:#6b7280;border:none;background:none;cursor:pointer;transition:all .2s;}
  .sub-tab.active{background:#fff;color:#ea580c;box-shadow:0 2px 8px rgba(0,0,0,.08);}
  .card{background:#fff;border-radius:16px;border:1px solid #f3f4f6;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.03);}
  .card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;}
  .section-title{font-size:19px;font-weight:800;margin:0;color:#111827;}
  .slide-form{display:none;background:#fff7ed;border:2px solid #fcd34d;border-radius:14px;padding:24px;margin-bottom:20px;}
  .slide-form.open{display:block;animation:sl .25s ease;}
  @keyframes sl{from{opacity:0;transform:translateY(-8px);}to{opacity:1;transform:translateY(0);}}
  .fg{margin-bottom:14px;}
  .fg label{display:block;font-weight:700;font-size:13px;color:#374151;margin-bottom:5px;}
  .fg input,.fg select,.fg textarea{width:100%;border:1px solid #fcd34d;border-radius:9px;padding:10px 13px;font-size:14px;font-family:'Outfit',sans-serif;outline:none;}
  .fg input:focus,.fg select:focus,.fg textarea:focus{border-color:#ea580c;box-shadow:0 0 0 3px rgba(124,58,237,.1);}
  .form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
  .upload-grid{display:grid;grid-template-columns:1.25fr .95fr;gap:18px;margin-top:18px;padding-top:18px;border-top:1px dashed #fcd34d;}
  .upload-note{background:#fff;border:1px dashed #fcd34d;border-radius:12px;padding:14px 16px;font-size:13px;color:#9a3412;line-height:1.6;}
  .btn{background:#ea580c;color:#fff;border:none;border-radius:9px;padding:10px 20px;font-weight:700;font-size:13px;cursor:pointer;font-family:'Outfit',sans-serif;display:inline-flex;align-items:center;gap:6px;text-decoration:none;}
  .btn:hover{background:#d97706;}
  .btn-outline{background:#fff;color:#ea580c;border:2px solid #ea580c;border-radius:9px;padding:8px 18px;font-weight:700;font-size:13px;cursor:pointer;font-family:'Outfit',sans-serif;display:inline-flex;align-items:center;gap:6px;text-decoration:none;}
  .btn-outline:hover{background:#fff7ed;}
  .btn-icon{background:none;border:none;cursor:pointer;font-size:19px;padding:4px 6px;display:inline-flex;color:#6b7280;border-radius:6px;}
  .btn-icon:hover{color:#ea580c;background:#fff7ed;}
  .btn-icon.danger:hover{color:#dc2626;background:#fef2f2;}
  .btn-sm{padding:5px 12px;font-size:12px;border-radius:7px;font-weight:700;cursor:pointer;border:none;font-family:'Outfit',sans-serif;display:inline-flex;align-items:center;gap:4px;}
  .btn-approve{background:#ecfdf5;color:#059669;border:1px solid #d1fae5;}
  .btn-reject{background:#fef2f2;color:#dc2626;border:1px solid #fee2e2;}
  table{width:100%;border-collapse:collapse;}
  th{padding:11px 14px;text-align:left;font-size:11px;font-weight:800;color:#6b7280;letter-spacing:.5px;text-transform:uppercase;background:#fff7ed;}
  td{padding:13px 14px;font-size:14px;border-bottom:1px solid #f3f4f6;color:#374151;vertical-align:middle;}
  tr:last-child td{border-bottom:none;}
  tr:hover td{background:#fffbf7;}
  .badge{padding:4px 10px;border-radius:20px;font-size:11px;font-weight:700;display:inline-block;}
  .b-invited{background:#eff6ff;color:#2563eb;} .b-pending{background:#fff7ed;color:#d97706;}
  .b-approved{background:#ecfdf5;color:#059669;} .b-rejected{background:#fef2f2;color:#dc2626;}
  .b-suspended{background:#f3f4f6;color:#6b7280;}
  .stat-mini{background:#fff;border:1px solid #ffedd5;border-radius:14px;padding:18px 20px;text-align:center;}
  .stat-mini .num{font-size:28px;font-weight:900;color:#ea580c;}
  .stat-mini .lbl{font-size:12px;font-weight:700;color:#6b7280;margin-top:2px;}
  .stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-bottom:24px;}
  .search-bar{display:flex;gap:8px;align-items:center;}
  .search-bar input{border:1px solid #e5e7eb;border-radius:9px;padding:8px 13px;font-size:13px;font-family:'Outfit',sans-serif;outline:none;min-width:200px;}
  .search-bar input:focus{border-color:#ea580c;}
  .modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:500;align-items:center;justify-content:center;}
  .modal-overlay.open{display:flex;}
  .modal-box{background:#fff;border-radius:16px;padding:28px;max-width:420px;width:90%;box-shadow:0 20px 50px rgba(0,0,0,.2);}
  @media(max-width:900px){.form-row,.upload-grid{grid-template-columns:1fr;}}
</style>
{% endblock %}

{% block content %}
<div style="margin-bottom:24px;">
  <h1 style="font-size:28px;font-weight:900;margin:0 0 4px;color:#111827;">Jury & Evaluation Management</h1>
  <p style="color:#6b7280;font-size:14px;margin:0;">Invite, review and manage evaluators (Jury & Expert) and evaluation criteria.</p>
</div>

<div class="sub-tabs">
  <a href="?sub=invitations" class="sub-tab {% if sub == 'invitations' or sub == 'expert_invitations' %}active{% endif %}">Invitations</a>
  <a href="?sub=jury_roster" class="sub-tab {% if sub == 'jury_roster' %}active{% endif %}">Jury Roster</a>
  <a href="?sub=expert_roster" class="sub-tab {% if sub == 'expert_roster' %}active{% endif %}">Expert Roster</a>
  <a href="?sub=evaluation" class="sub-tab {% if sub == 'evaluation' %}active{% endif %}">Evaluation Assignments</a>
</div>

<!-- ════════════════════════════════
     SUB-TAB: INVITATIONS
════════════════════════════════ -->
{% if sub == 'invitations' or sub == 'expert_invitations' %}

<div class="stats-row">
  <div class="stat-mini"><div class="num">{{ invite_counts.invited|add:expert_invite_counts.invited }}</div><div class="lbl">Invited</div></div>
  <div class="stat-mini"><div class="num">{{ invite_counts.pending|add:expert_invite_counts.pending }}</div><div class="lbl">Pending Review</div></div>
  <div class="stat-mini"><div class="num">{{ invite_counts.approved|add:expert_invite_counts.approved }}</div><div class="lbl">Approved</div></div>
  <div class="stat-mini"><div class="num">{{ juries|length|add:experts|length }}</div><div class="lbl">Active Evaluators</div></div>
</div>

<!-- Send Invite slide form -->
<div id="inviteForm" class="slide-form">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;">
    <h3 style="margin:0;color:#ea580c;font-weight:800;">Send Evaluator Invitation</h3>
    <button type="button" onclick="document.getElementById('inviteForm').classList.remove('open')" style="background:none;border:none;font-size:24px;cursor:pointer;color:#9ca3af;"><ion-icon name="close-circle-outline"></ion-icon></button>
  </div>
  <form method="POST" action="{% url 'send_evaluator_invite' %}">
    {% csrf_token %}
    <div class="form-row">
      <div class="fg">
        <label>Email Address *</label>
        <input type="email" name="email" placeholder="e.g. evaluator@university.edu" required>
      </div>
      <div class="fg">
        <label>Role *</label>
        <select name="role" required>
            <option value="jury">Jury</option>
            <option value="expert">Expert</option>
        </select>
      </div>
    </div>
    <div class="fg">
        <label>Target Hackathon <span style="font-size:11px;color:#9ca3af;">(optional)</span></label>
        <select name="hackathon_id">
          <option value="">-- Select Hackathon --</option>
          {% for h in hackathons %}<option value="{{ h.id }}">{{ h.name }}</option>{% endfor %}
        </select>
    </div>
    <div style="display:flex;gap:12px;">
      <button type="submit" class="btn"><ion-icon name="send-outline"></ion-icon> Send Invitation</button>
      <button type="button" class="btn-outline" onclick="document.getElementById('inviteForm').classList.remove('open')">Cancel</button>
    </div>
  </form>
  <!-- Bulk CSV -->
  <div class="upload-grid">
    <form method="POST" action="{% url 'send_bulk_evaluator_invites' %}" enctype="multipart/form-data">
      {% csrf_token %}
      <div class="fg">
        <label>Bulk Invite via CSV</label>
        <input type="file" name="csv_file" accept=".csv" required>
      </div>
      <div class="form-row">
          <div class="fg">
            <label>Role *</label>
            <select name="role" required>
                <option value="jury">Jury</option>
                <option value="expert">Expert</option>
            </select>
          </div>
          <div class="fg">
            <label>Target Hackathon <span style="font-size:11px;color:#9ca3af;">(optional)</span></label>
            <select name="hackathon_id">
              <option value="">-- Select Hackathon --</option>
              {% for h in hackathons %}<option value="{{ h.id }}">{{ h.name }}</option>{% endfor %}
            </select>
          </div>
      </div>
      <button type="submit" class="btn"><ion-icon name="cloud-upload-outline"></ion-icon> Send Bulk Invitations</button>
    </form>
    <div class="upload-note">
      <strong>CSV Format</strong>
      Use a column named <code>email</code> or one email per row. Duplicates, existing users, and invalid emails are skipped automatically.
    </div>
  </div>
</div>

<!-- Invitations table -->
<div class="card">
  <div class="card-header">
    <h2 class="section-title">Evaluator Invitations</h2>
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
      <form method="GET" class="search-bar">
        <input type="hidden" name="sub" value="invitations">
        <input type="text" name="q" placeholder="Search email / name..." value="{{ q }}">
      </form>
      <button class="btn" onclick="document.getElementById('inviteForm').classList.toggle('open')">
        <ion-icon name="add-outline"></ion-icon> Invite Evaluator
      </button>
    </div>
  </div>
  <table>
    <thead><tr><th>ROLE</th><th>EMAIL</th><th>NAME / ORG</th><th>HACKATHON</th><th>STATUS</th><th>ACTIONS</th></tr></thead>
    <tbody>
      <!-- Jury Invitations -->
      {% for inv in invitations %}
      <tr>
        <td><span class="badge" style="background:#f3e8ff;color:#7e22ce;">Jury</span></td>
        <td><strong>{{ inv.email }}</strong></td>
        <td>
          {% if inv.first_name %}{{ inv.first_name }} {{ inv.last_name }}<br><small style="color:#6b7280;">{{ inv.organization|default:"—" }}</small>
          {% else %}<span style="color:#9ca3af;font-style:italic;">Not submitted yet</span>{% endif %}
        </td>
        <td>{{ inv.hackathon.name|default:"—" }}</td>
        <td>
          <span class="badge {% if inv.status == 'invited' %}b-invited{% elif inv.status == 'pending' %}b-pending{% elif inv.status == 'approved' %}b-approved{% elif inv.status == 'suspended' %}b-suspended{% else %}b-rejected{% endif %}">
            {{ inv.get_status_display }}
          </span>
        </td>
        <td>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
            <a href="{% url 'view_jury_invitation' inv.id %}" class="btn-icon" title="View"><ion-icon name="eye-outline"></ion-icon></a>
            {% if inv.status != 'approved' %}
            <a href="{% url 'edit_jury_invitation' inv.id %}" class="btn-icon" title="Edit"><ion-icon name="create-outline"></ion-icon></a>
            <form method="POST" action="{% url 'suspend_jury_invitation' inv.id %}" style="display:inline;" onsubmit="return confirm('{% if inv.status == 'suspended' %}Reactivate{% else %}Suspend{% endif %} application for {{ inv.email }}?')">
              {% csrf_token %}
              <button class="btn-icon danger" title="{% if inv.status == 'suspended' %}Reactivate{% else %}Suspend{% endif %}" type="submit">
                <ion-icon name="{% if inv.status == 'suspended' %}checkmark-circle-outline{% else %}ban-outline{% endif %}"></ion-icon>
              </button>
            </form>
            {% endif %}
            {% if inv.status == 'pending' %}
            <form method="POST" action="{% url 'approve_jury_invitation' inv.id %}" style="display:inline;">{% csrf_token %}<button class="btn-sm btn-approve">Approve</button></form>
            <button class="btn-sm btn-reject" onclick="openRejectModal({{ inv.id }},'{{ inv.email }}', 'jury')">Reject</button>
            {% elif inv.status == 'approved' and inv.created_user %}
            <a href="{% url 'view_jury_member' inv.created_user.jury_profile.id %}" class="btn-sm btn-approve">Profile</a>
            {% endif %}
          </div>
        </td>
      </tr>
      {% endfor %}
      
      <!-- Expert Invitations -->
      {% for inv in expert_invitations %}
      <tr>
        <td><span class="badge" style="background:#ffedd5;color:#ea580c;">Expert</span></td>
        <td><strong>{{ inv.email }}</strong></td>
        <td>
          {% if inv.first_name %}{{ inv.first_name }} {{ inv.last_name }}<br><small style="color:#6b7280;">{{ inv.organization|default:"—" }}</small>
          {% else %}<span style="color:#9ca3af;font-style:italic;">Not submitted yet</span>{% endif %}
        </td>
        <td>{{ inv.hackathon.name|default:"—" }}</td>
        <td>
          <span class="badge {% if inv.status == 'invited' %}b-invited{% elif inv.status == 'pending' %}b-pending{% elif inv.status == 'approved' %}b-approved{% elif inv.status == 'suspended' %}b-suspended{% else %}b-rejected{% endif %}">
            {{ inv.get_status_display }}
          </span>
        </td>
        <td>
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
            <a href="{% url 'view_expert_invitation' inv.id %}" class="btn-icon" title="View"><ion-icon name="eye-outline"></ion-icon></a>
            {% if inv.status != 'approved' %}
            <a href="{% url 'edit_expert_invitation' inv.id %}" class="btn-icon" title="Edit"><ion-icon name="create-outline"></ion-icon></a>
            <form method="POST" action="{% url 'suspend_expert_invitation' inv.id %}" style="display:inline;" onsubmit="return confirm('{% if inv.status == 'suspended' %}Reactivate{% else %}Suspend{% endif %} application for {{ inv.email }}?')">
              {% csrf_token %}
              <button class="btn-icon danger" title="{% if inv.status == 'suspended' %}Reactivate{% else %}Suspend{% endif %}" type="submit">
                <ion-icon name="{% if inv.status == 'suspended' %}checkmark-circle-outline{% else %}ban-outline{% endif %}"></ion-icon>
              </button>
            </form>
            {% endif %}
            {% if inv.status == 'pending' %}
            <form method="POST" action="{% url 'approve_expert_invitation' inv.id %}" style="display:inline;">{% csrf_token %}<button class="btn-sm btn-approve">Approve</button></form>
            <button class="btn-sm btn-reject" onclick="openRejectModal({{ inv.id }},'{{ inv.email }}', 'expert')">Reject</button>
            {% elif inv.status == 'approved' and inv.created_user %}
            <a href="{% url 'view_expert_member' inv.created_user.expert_profile.id %}" class="btn-sm btn-approve">Profile</a>
            {% endif %}
          </div>
        </td>
      </tr>
      {% endfor %}
      
      {% if not invitations and not expert_invitations %}
      <tr><td colspan="6" style="text-align:center;padding:40px;color:#9ca3af;">No invitations yet. Click "Invite Evaluator" to get started.</td></tr>
      {% endif %}
    </tbody>
  </table>
</div>

<!-- ════════════════════════════════
     SUB-TAB: JURY ROSTER
════════════════════════════════ -->
{% elif sub == 'jury_roster' %}
<div class="card">
  <div class="card-header">
    <h2 class="section-title">Active Jury Members</h2>
    <form method="GET" class="search-bar">
      <input type="hidden" name="sub" value="jury_roster">
      <input type="text" name="q" placeholder="Search name / domain..." value="{{ q }}">
    </form>
  </div>
  <table>
    <thead><tr><th>JURY MEMBER</th><th>EMAIL</th><th>DOMAIN</th><th>ASSIGNED TEAMS</th><th>STATUS</th><th>ACTIONS</th></tr></thead>
    <tbody>
      {% for jury in juries %}
      <tr>
        <td>
          <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:36px;height:36px;background:#ffedd5;border-radius:10px;display:flex;align-items:center;justify-content:center;color:#ea580c;font-weight:800;font-size:15px;">
              {{ jury.user.username|slice:":1"|upper }}
            </div>
            <div>
              <strong>{{ jury.user.get_full_name|default:jury.user.username }}</strong><br>
              <small style="color:#6b7280;font-family:monospace;">@{{ jury.user.username }}</small>
            </div>
          </div>
        </td>
        <td>{{ jury.user.email }}</td>
        <td>{{ jury.domain|default:"—" }}</td>
        <td><span style="font-weight:700; color:#ea580c;">{{ jury.assigned_teams_count }} teams</span></td>
        <td>
          {% if jury.user.is_active %}<span class="badge b-approved">Active</span>
          {% else %}<span class="badge b-suspended">Suspended</span>{% endif %}
        </td>
        <td>
          <div style="display:flex;gap:6px;">
            <a href="{% url 'view_jury_member' jury.id %}" class="btn-icon" title="View"><ion-icon name="eye-outline"></ion-icon></a>
            <a href="{% url 'edit_jury_member' jury.id %}" class="btn-icon" title="Edit"><ion-icon name="create-outline"></ion-icon></a>
            <form method="POST" action="{% url 'toggle_jury_member_status' jury.id %}" style="display:inline;" onsubmit="return confirm('{% if jury.user.is_active %}Suspend{% else %}Reactivate{% endif %} {{ jury.user.email }}?')">
              {% csrf_token %}
              <button class="btn-icon danger" title="{% if jury.user.is_active %}Suspend{% else %}Reactivate{% endif %}" type="submit">
                <ion-icon name="{% if jury.user.is_active %}ban-outline{% else %}checkmark-circle-outline{% endif %}"></ion-icon>
              </button>
            </form>
          </div>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="6" style="text-align:center;padding:40px;color:#9ca3af;">No jury members yet. Approve invitations to populate the roster.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<!-- ════════════════════════════════
     SUB-TAB: EXPERT ROSTER
════════════════════════════════ -->
{% elif sub == 'expert_roster' %}
<div class="card">
  <div class="card-header">
    <h2 class="section-title">Active Expert Members</h2>
    <form method="GET" class="search-bar">
      <input type="hidden" name="sub" value="expert_roster">
      <input type="text" name="q" placeholder="Search name / domain..." value="{{ q }}">
    </form>
  </div>
  <table>
    <thead><tr><th>EXPERT MEMBER</th><th>EMAIL</th><th>DOMAIN</th><th>ASSIGNED TEAMS</th><th>STATUS</th><th>ACTIONS</th></tr></thead>
    <tbody>
      {% for expert in experts %}
      <tr>
        <td>
          <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:36px;height:36px;background:#ffedd5;border-radius:10px;display:flex;align-items:center;justify-content:center;color:#ea580c;font-weight:800;font-size:15px;">
              {{ expert.user.username|slice:":1"|upper }}
            </div>
            <div>
              <strong>{{ expert.user.get_full_name|default:expert.user.username }}</strong><br>
              <small style="color:#6b7280;font-family:monospace;">@{{ expert.user.username }}</small>
            </div>
          </div>
        </td>
        <td>{{ expert.user.email }}</td>
        <td>{{ expert.domain|default:"—" }}</td>
        <td><span style="font-weight:700; color:#ea580c;">{{ expert.assigned_teams_count }} teams</span></td>
        <td>
          {% if expert.user.is_active %}<span class="badge b-approved">Active</span>
          {% else %}<span class="badge b-suspended">Suspended</span>{% endif %}
        </td>
        <td>
          <div style="display:flex;gap:6px;">
            <a href="{% url 'view_expert_member' expert.id %}" class="btn-icon" title="View"><ion-icon name="eye-outline"></ion-icon></a>
            <a href="{% url 'edit_expert_member' expert.id %}" class="btn-icon" title="Edit"><ion-icon name="create-outline"></ion-icon></a>
            <form method="POST" action="{% url 'toggle_expert_member_status' expert.id %}" style="display:inline;" onsubmit="return confirm('{% if expert.user.is_active %}Suspend{% else %}Reactivate{% endif %} {{ expert.user.email }}?')">
              {% csrf_token %}
              <button class="btn-icon danger" title="{% if expert.user.is_active %}Suspend{% else %}Reactivate{% endif %}" type="submit">
                <ion-icon name="{% if expert.user.is_active %}ban-outline{% else %}checkmark-circle-outline{% endif %}"></ion-icon>
              </button>
            </form>
          </div>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="6" style="text-align:center;padding:40px;color:#9ca3af;">No expert members yet. Approve invitations to populate the roster.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>


<!-- ════════════════════════════════
     SUB-TAB: EVALUATION
════════════════════════════════ -->
{% elif sub == 'evaluation' %}
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px;">
  <div></div>
  <form method="GET">
    <input type="hidden" name="sub" value="evaluation">
    <select name="hackathon" onchange="this.form.submit()" style="border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px;font-family:'Outfit',sans-serif;">
      <option value="">Select hackathon</option>
      {% for h in hackathons %}<option value="{{ h.id }}" {% if hackathon_filter == h.id|stringformat:"s" %}selected{% endif %}>{{ h.name }}</option>{% endfor %}
    </select>
  </form>
</div>

<div class="stats-row">
  <div class="stat-mini"><div class="num">{{ registration_counts.teams|default:0 }}</div><div class="lbl">Teams in Scope</div></div>
  <div class="stat-mini"><div class="num">{{ registration_counts.approved|default:0 }}</div><div class="lbl">Approved</div></div>
  <div class="stat-mini"><div class="num">{{ registration_counts.submitted|default:0 }}</div><div class="lbl">Submitted</div></div>
  <div class="stat-mini"><div class="num">{{ registration_counts.evaluated|default:0 }}</div><div class="lbl">Evaluated</div></div>
</div>

<!-- Marking Parameters -->
<div class="card">
  <h2 class="section-title" style="margin-bottom:16px;">Round Marking Parameters</h2>
  {% if active_hackathon %}
  <form method="POST" action="{% url 'save_marking_parameter' %}" style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;">
    {% csrf_token %}
    <input type="hidden" name="hackathon_id" value="{{ active_hackathon.id }}">
    <select name="round_number" style="border:1px solid #fcd34d;border-radius:9px;padding:9px 12px;font-family:'Outfit',sans-serif;">
      {% for r in round_range %}<option value="{{ r }}">Round {{ r }}</option>{% endfor %}
    </select>
    <input name="name" placeholder="Parameter name e.g. Innovation" required style="border:1px solid #fcd34d;border-radius:9px;padding:9px 12px;flex:1;min-width:180px;font-family:'Outfit',sans-serif;">
    <button class="btn" type="submit"><ion-icon name="add-circle-outline"></ion-icon> Add Parameter</button>
  </form>
  <table>
    <thead><tr><th>ROUND</th><th>PARAMETER NAME</th><th>ACTION</th></tr></thead>
    <tbody>
      {% for p in parameters %}
      <tr>
        <td><span class="badge b-invited">Round {{ p.round_number }}</span></td>
        <td>{{ p.name }}</td>
        <td>
          <form method="POST" action="{% url 'delete_marking_parameter' p.id %}" style="display:inline;" onsubmit="return confirm('Delete parameter?')">
            {% csrf_token %}<button class="btn-icon danger" type="submit"><ion-icon name="trash-outline"></ion-icon></button>
          </form>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="3" style="text-align:center;color:#9ca3af;">No parameters configured yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p style="color:#9ca3af;">Select a hackathon above to manage evaluation parameters.</p>
  {% endif %}
</div>

<!-- Evaluation Readiness -->
<div class="card">
  <h2 class="section-title" style="margin-bottom:16px;">Evaluation Readiness Snapshot</h2>
  <table>
    
    <thead><tr><th>TEAM</th><th>INSTITUTION</th><th>PROBLEM STATEMENT</th><th>STATUS</th><th>ASSIGNMENTS</th></tr></thead>
    <tbody>
      {% for team in teams_for_eval %}
      <tr>
        <td><strong>{{ team.team_name }}</strong></td>
        <td>{{ team.institution.name|default:"—" }}</td>
        <td>{{ team.problem_statement.title|default:"—" }}</td>
        <td><span class="badge b-{% if team.eval_status == 'Assigned' %}approved{% else %}pending{% endif %}">{{ team.eval_status }}</span></td>
        <td>
            {% if team.eval_assignment %}
                <div style="font-size:12px;color:#6b7280;margin-bottom:6px;">
                    <strong>Round {{ team.eval_assignment.round_number }}</strong>:
                    {% if team.eval_assignment.jury_1 %}J1, {% endif %}
                    {% if team.eval_assignment.jury_2 %}J2, {% endif %}
                    {% if team.eval_assignment.jury_3 %}J3, {% endif %}
                    {% if team.eval_assignment.expert %}Expert{% endif %}
                </div>
            {% endif %}
            <button class="btn-sm btn-outline" onclick="openAssignModal({{ team.id }}, '{{ team.team_name|escapejs }}', {{ team.eval_assignment.round_number|default:1 }}, {{ team.eval_assignment.jury_1_id|default:'null' }}, {{ team.eval_assignment.jury_2_id|default:'null' }}, {{ team.eval_assignment.jury_3_id|default:'null' }}, {{ team.eval_assignment.expert_id|default:'null' }})">Assign Evaluators</button>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="5" style="text-align:center;padding:32px;color:#9ca3af;">No teams available for evaluation yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

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

<!-- Reject Modal -->
<div class="modal-overlay" id="rejectModal">
  <div class="modal-box">
    <h3 style="margin:0 0 8px;">Reject Application</h3>
    <p id="rejectEmailText" style="color:#6b7280;font-size:14px;margin-bottom:16px;"></p>
    <form id="rejectForm" method="POST">
      {% csrf_token %}
      <div class="fg"><label>Reason for Rejection</label><input type="text" name="rejection_reason" placeholder="Optional reason..."></div>
      <div style="display:flex;gap:10px;margin-top:16px;">
        <button type="submit" class="btn-sm btn-reject" style="padding:9px 18px;">Confirm Reject</button>
        <button type="button" onclick="document.getElementById('rejectModal').classList.remove('open')" class="btn-outline">Cancel</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
function openRejectModal(id, email, role) {
  document.getElementById('rejectEmailText').textContent = 'Rejecting invitation for: ' + email;
  if (role === 'expert') {
      document.getElementById('rejectForm').action = '/features/expert/invitation/' + id + '/reject/';
  } else {
      document.getElementById('rejectForm').action = '/features/jury/invitation/' + id + '/reject/';
  }
  document.getElementById('rejectModal').classList.add('open');
}

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
</script>
{% endblock %}
"""

with open(r'd:\OKCL\Hackathon\code\Bput-Hackathon\features\templates\features\jury_management.html', 'w', encoding='utf-8') as f:
    f.write(template_content)

print("Template written successfully")
