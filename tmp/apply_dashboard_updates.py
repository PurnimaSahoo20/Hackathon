import os

path = r'd:/OKCL/Hackathon/code/Bput-Hackathon/accounts/templates/accounts/superadmin_dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. ADMIN MANAGEMENT
# Search Header Admin
old_admin_header = '''                <!-- BOTTOM: ADMIN LIST -->
                <div style="margin-top: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                        <h2 class="section-title" style="margin: 0; font-size: 20px; font-weight: 800;">Existing Administrators</h2>
                        <form method="GET" action="/accounts/dashboard/" style="display: flex; gap: 8px;">
                            <input type="hidden" name="tab" value="admin_mgt">
                            <input type="text" name="search_admins" value="{{ search_admins }}" placeholder="Search admins..." 
                                style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; font-size: 14px; outline: none; width: 250px;">
                            <button type="submit" style="background: #ea580c; color: white; border: none; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 600;">Search</button>
                            {% if search_admins %}
                                <a href="?tab=admin_mgt" style="background: #f3f4f6; color: #4b5563; border: none; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 600; text-decoration: none;">Clear</a>
                            {% endif %}
                        </form>
                    </div>'''
# (Search header was already applied in a previous step, so we check if it needs update or just proceed to cells)

# Admin Name Strikeout
old_admin_name = '<div style="font-weight: 800; color: #111827;">{{ admin.user.get_full_name }}</div>'
new_admin_name = '<div style="{% if not admin.user.is_active %}text-decoration: line-through; color: #9ca3af;{% endif %} font-weight: 800; color: #111827;">{{ admin.user.get_full_name }}</div>'
content = content.replace(old_admin_name, new_admin_name)

# Admin Suspend Link
old_admin_delete = '<a href="{% url \'delete_user\' admin.user.id %}" onclick="return confirm(\'Delete this Admin?\')" title="Delete" style="color: #dc2626; font-size: 18px;"><ion-icon name="trash"></ion-icon></a>'
new_admin_delete = '<a href="{% url \'delete_user\' admin.user.id %}" onclick="return confirm(\'Suspend this Admin?\')" title="Suspend" style="color: #dc2626; font-size: 18px;"><ion-icon name="ban-outline"></ion-icon></a>'
content = content.replace(old_admin_delete, new_admin_delete)

# Admin Pagination
old_admin_table_end = '''                                <tr><td colspan="4" style="text-align:center; padding: 40px; color: #6b7280;">No Admins onboarded yet.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>'''
new_admin_table_end = '''                                <tr><td colspan="4" style="text-align:center; padding: 40px; color: #6b7280;">No Admins found.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>

                    <!-- Pagination for Admins -->
                    {% if admins_list.paginator.num_pages > 1 %}
                    <div style="display: flex; justify-content: center; gap: 8px; margin-top: 24px;">
                        {% if admins_list.has_previous %}
                            <a href="?tab=admin_mgt&page={{ admins_list.previous_page_number }}{% if search_admins %}&search_admins={{ search_admins }}{% endif %}" 
                               style="padding: 8px 12px; border-radius: 6px; border: 1px solid #e5e7eb; background: white; color: #374151; text-decoration: none; font-weight: 600;">Previous</a>
                        {% endif %}
                        
                        <span style="padding: 8px 12px; color: #374151; font-weight: 600;">Page {{ admins_list.number }} of {{ admins_list.paginator.num_pages }}</span>
                        
                        {% if admins_list.has_next %}
                            <a href="?tab=admin_mgt&page={{ admins_list.next_page_number }}{% if search_admins %}&search_admins={{ search_admins }}{% endif %}" 
                               style="padding: 8px 12px; border-radius: 6px; border: 1px solid #e5e7eb; background: white; color: #374151; text-decoration: none; font-weight: 600;">Next</a>
                        {% endif %}
                    </div>
                    {% endif %}'''
content = content.replace(old_admin_table_end, new_admin_table_end)


# 2. EXECUTIVE MANAGEMENT
# Search Header Executive
old_exec_header = '''                <!-- BOTTOM: EXECUTIVE LIST -->
                <div style="margin-top: 50px;">
                    <h2 class="section-title" style="margin-bottom: 20px; font-size: 22px; font-weight: 800;">Hackathon Executives</h2>'''
new_exec_header = '''                <!-- BOTTOM: EXECUTIVE LIST -->
                <div style="margin-top: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                        <h2 class="section-title" style="margin: 0; font-size: 20px; font-weight: 800;">Hackathon Executives</h2>
                        <form method="GET" action="/accounts/dashboard/" style="display: flex; gap: 8px;">
                            <input type="hidden" name="tab" value="exec_mgt">
                            <input type="text" name="search_execs" value="{{ search_execs }}" placeholder="Search executives..." 
                                style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; font-size: 14px; outline: none; width: 250px;">
                            <button type="submit" style="background: #ea580c; color: white; border: none; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 600;">Search</button>
                            {% if search_execs %}
                                <a href="?tab=exec_mgt" style="background: #f3f4f6; color: #4b5563; border: none; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 600; text-decoration: none;">Clear</a>
                            {% endif %}
                        </form>
                    </div>'''
content = content.replace(old_exec_header.strip(), new_exec_header.strip())

# Executive Name Strikeout
old_exec_name = '<div style="font-weight: 800; color: #111827;">{{ exec.user.get_full_name }}</div>'
new_exec_name = '<div style="{% if not exec.user.is_active %}text-decoration: line-through; color: #9ca3af;{% endif %} font-weight: 800; color: #111827;">{{ exec.user.get_full_name }}</div>'
content = content.replace(old_exec_name, new_exec_name)

# Executive Suspend Link
old_exec_delete = '<a href="{% url \'delete_user\' exec.user.id %}" onclick="return confirm(\'Delete this Executive?\')" title="Delete" style="color: #dc2626; font-size: 18px;"><ion-icon name="trash"></ion-icon></a>'
new_exec_delete = '<a href="{% url \'delete_user\' exec.user.id %}" onclick="return confirm(\'Suspend this Executive?\')" title="Suspend" style="color: #dc2626; font-size: 18px;"><ion-icon name="ban-outline"></ion-icon></a>'
content = content.replace(old_exec_delete, new_exec_delete)

# Executive Pagination
old_exec_table_end = '''                                <tr><td colspan="4" style="text-align:center; padding: 40px; color: #6b7280;">No Executives found.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>'''
new_exec_table_end = '''                                <tr><td colspan="4" style="text-align:center; padding: 40px; color: #6b7280;">No Executives found.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>

                    <!-- Pagination for Executives -->
                    {% if executives_list.paginator.num_pages > 1 %}
                    <div style="display: flex; justify-content: center; gap: 8px; margin-top: 24px;">
                        {% if executives_list.has_previous %}
                            <a href="?tab=exec_mgt&page={{ executives_list.previous_page_number }}{% if search_execs %}&search_execs={{ search_execs }}{% endif %}" 
                               style="padding: 8px 12px; border-radius: 6px; border: 1px solid #e5e7eb; background: white; color: #374151; text-decoration: none; font-weight: 600;">Previous</a>
                        {% endif %}
                        
                        <span style="padding: 8px 12px; color: #374151; font-weight: 600;">Page {{ executives_list.number }} of {{ executives_list.paginator.num_pages }}</span>
                        
                        {% if executives_list.has_next %}
                            <a href="?tab=exec_mgt&page={{ executives_list.next_page_number }}{% if search_execs %}&search_execs={{ search_execs }}{% endif %}" 
                               style="padding: 8px 12px; border-radius: 6px; border: 1px solid #e5e7eb; background: white; color: #374151; text-decoration: none; font-weight: 600;">Next</a>
                        {% endif %}
                    </div>
                    {% endif %}'''
content = content.replace(old_exec_table_end, new_exec_table_end)


# 3. EXPERT USER MANAGEMENT
# Search Header User
old_user_header = '''                <!-- BOTTOM: USER LIST -->
                <div style="margin-top: 50px;">
                    <h2 class="section-title" style="margin-bottom: 20px; font-size: 22px; font-weight: 800;">Onboarded Users (Experts/Leads)</h2>'''
new_user_header = '''                <!-- BOTTOM: USER LIST -->
                <div style="margin-top: 16px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                        <h2 class="section-title" style="margin: 0; font-size: 20px; font-weight: 800;">Onboarded Users (Experts/Leads)</h2>
                        <form method="GET" action="/accounts/dashboard/" style="display: flex; gap: 8px;">
                            <input type="hidden" name="tab" value="user_mgt">
                            <input type="text" name="search_users" value="{{ search_users }}" placeholder="Search users..." 
                                style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; font-size: 14px; outline: none; width: 250px;">
                            <button type="submit" style="background: #ea580c; color: white; border: none; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 600;">Search</button>
                            {% if search_users %}
                                <a href="?tab=user_mgt" style="background: #f3f4f6; color: #4b5563; border: none; border-radius: 8px; padding: 10px 16px; cursor: pointer; font-weight: 600; text-decoration: none;">Clear</a>
                            {% endif %}
                        </form>
                    </div>'''
content = content.replace(old_user_header.strip(), new_user_header.strip())

# User Name Strikeout
old_user_name = '<div style="font-weight: 800; color: #111827;">{{ user.get_full_name }}</div>'
new_user_name = '<div style="{% if not user.is_active %}text-decoration: line-through; color: #9ca3af;{% endif %} font-weight: 800; color: #111827;">{{ user.get_full_name }}</div>'
content = content.replace(old_user_name, new_user_name)

# User Suspend Link
old_user_delete = '<a href="{% url \'delete_user\' user.id %}" onclick="return confirm(\'Delete this User?\')" title="Delete" style="color: #dc2626; font-size: 18px;"><ion-icon name="trash"></ion-icon></a>'
new_user_delete = '<a href="{% url \'delete_user\' user.id %}" onclick="return confirm(\'Suspend this User?\')" title="Suspend" style="color: #dc2626; font-size: 18px;"><ion-icon name="ban-outline"></ion-icon></a>'
content = content.replace(old_user_delete, new_user_delete)

# User Pagination
old_user_table_end = '''                                <tr><td colspan="4" style="text-align:center; padding: 40px; color: #6b7280;">No other users onboarded.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>'''
new_user_table_end = '''                                <tr><td colspan="4" style="text-align:center; padding: 40px; color: #6b7280;">No expert users found.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>

                    <!-- Pagination for Expert Users -->
                    {% if other_users_list.paginator.num_pages > 1 %}
                    <div style="display: flex; justify-content: center; gap: 8px; margin-top: 24px;">
                        {% if other_users_list.has_previous %}
                            <a href="?tab=user_mgt&page={{ other_users_list.previous_page_number }}{% if search_users %}&search_users={{ search_users }}{% endif %}" 
                               style="padding: 8px 12px; border-radius: 6px; border: 1px solid #e5e7eb; background: white; color: #374151; text-decoration: none; font-weight: 600;">Previous</a>
                        {% endif %}
                        
                        <span style="padding: 8px 12px; color: #374151; font-weight: 600;">Page {{ other_users_list.number }} of {{ other_users_list.paginator.num_pages }}</span>
                        
                        {% if other_users_list.has_next %}
                            <a href="?tab=user_mgt&page={{ other_users_list.next_page_number }}{% if search_users %}&search_users={{ search_users }}{% endif %}" 
                               style="padding: 8px 12px; border-radius: 6px; border: 1px solid #e5e7eb; background: white; color: #374151; text-decoration: none; font-weight: 600;">Next</a>
                        {% endif %}
                    </div>
                    {% endif %}'''
content = content.replace(old_user_table_end.strip(), new_user_table_end.strip())

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Finished updates.")
