import re

with open('events/templates/events/edit_hackathon.html', 'r', encoding='utf-8') as f:
    content = f.read()

for i in range(1, 6):
    target = f'<div class="form-grid"><div class="form-group"><label>Start Date</label><input type="date" name="round_{i}_start_date" value="{{{{ hackathon.round_{i}_start_date|date:\'Y-m-d\' }}}}"></div><div class="form-group"><label>End Date</label><input type="date" name="round_{i}_end_date" value="{{{{ hackathon.round_{i}_end_date|date:\'Y-m-d\' }}}}"></div></div>'
    
    replacement = target + f'''
                <div style="width: 100%; border-top: 1px dashed #fed7aa; padding-top: 14px; margin-top: 4px;">
                    <div style="display:flex; gap:14px; align-items:center; margin-bottom: 10px;">
                        <div class="form-group" style="margin:0; max-width: 250px;">
                            <label>No. of Marking Parameters</label>
                            <input type="number" name="round_{i}_num_params" value="{{{{ round_params.{i}.count|default:0 }}}}" min="0" oninput="updateMarkingParams(this, {i})">
                        </div>
                        <label style="display:flex; align-items:center; gap:8px; font-weight:700; color:#374151; margin-top: 22px;">
                            <input type="checkbox" name="round_{i}_has_others" style="width:16px; height:16px; accent-color:#ea580c;" {{{{ round_params.{i}.has_others|yesno:'checked,' }}}}> Include 'Others' Option
                        </label>
                    </div>
                    <div id="round_{i}_params_container" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:10px;">
                        {{% for p in round_params.{i}.params %}}
                        <div class="form-group" style="margin-bottom:0;">
                            <label style="font-size:11px;">Parameter {{{{ forloop.counter }}}}</label>
                            <input type="text" name="round_{i}_param_{{{{ forloop.counter }}}}_name" value="{{{{ p.name }}}}" required>
                        </div>
                        {{% endfor %}}
                    </div>
                </div>'''
    content = content.replace(target, replacement)

js_addition = '''
    function updateMarkingParams(inputElem, roundNum) {
        const count = parseInt(inputElem.value) || 0;
        const container = document.getElementById(`round_${roundNum}_params_container`);
        if (!container) return;
        
        const existingInputs = container.querySelectorAll('input[type="text"]');
        const values = Array.from(existingInputs).map(input => input.value);
        
        container.innerHTML = '';
        for (let j = 1; j <= count; j++) {
            const div = document.createElement('div');
            div.className = 'form-group';
            div.style.marginBottom = '0';
            const val = values[j-1] ? `value="${values[j-1]}"` : '';
            div.innerHTML = `<label style="font-size:11px;">Parameter ${j}</label>
                             <input type="text" name="round_${roundNum}_param_${j}_name" required ${val} placeholder="e.g. Innovation">`;
            container.appendChild(div);
        }
    }
</script>'''

content = content.replace('</script>', js_addition)

with open('events/templates/events/edit_hackathon.html', 'w', encoding='utf-8') as f:
    f.write(content)
