import re

def update_css():
    with open('static/site.css', 'r', encoding='utf-8') as f:
        css = f.read()

    # 1. Pulse Critical
    # Remove old pulseCritical if it exists
    css = re.sub(r'@keyframes pulseCritical \{.*?\}', '', css, flags=re.DOTALL)
    css = re.sub(r'animation: pulseCritical.*?;', '', css)

    pulse_css = """
@keyframes pulse-critical {
    0% { opacity: 1; }
    50% { opacity: 0.75; }
    100% { opacity: 1; }
}
@media (prefers-reduced-motion: no-preference) {
    .badge.danger, .status-yes {
        animation: pulse-critical 2s infinite ease-in-out;
    }
}
"""
    if "@keyframes pulse-critical" not in css:
        css += pulse_css

    # 2. Alert Slide Fade
    # Remove old slideFadeIn
    css = re.sub(r'@keyframes slideFadeIn \{.*?\}', '', css, flags=re.DOTALL)
    css = re.sub(r'\.new-alert \{.*?\}', '', css, flags=re.DOTALL)

    slide_css = """
@keyframes alert-slide-fade {
    0% { transform: translateY(-8px); opacity: 0; background-color: rgba(37, 99, 235, 0.4); }
    20% { transform: translateY(0); opacity: 1; }
    100% { background-color: transparent; opacity: 1; }
}
@media (prefers-reduced-motion: no-preference) {
    .is-new {
        animation: alert-slide-fade 1.5s ease-out forwards;
    }
}
"""
    if "@keyframes alert-slide-fade" not in css:
        css += slide_css

    # 5. Skeleton Loaders
    skeleton_css = """
@keyframes shimmer-sweep {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
.skeleton-loader {
    background: linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%);
    background-size: 200% 100%;
    animation: shimmer-sweep 1.5s infinite linear;
    border-radius: 4px;
    height: 100%;
    width: 100%;
    display: inline-block;
    min-height: 20px;
}
"""
    if "@keyframes shimmer-sweep" not in css:
        css += skeleton_css

    with open('static/site.css', 'w', encoding='utf-8') as f:
        f.write(css)


def update_dashboard_js():
    with open('static/dashboard.js', 'r', encoding='utf-8') as f:
        js = f.read()

    # Rename animateValue to animateCountUp and ensure correct logic
    js = js.replace('function animateValue', 'function animateCountUp')
    js = js.replace("animateValue(", "animateCountUp(")
    
    # 2. Update renderAlerts to use .is-new and remove it via setTimeout
    # I previously used .new-alert
    js = js.replace("const animCls = isNew ? 'new-alert' : '';", "const animCls = isNew ? 'is-new' : '';")
    js = js.replace("return `<div class=\"alert-item ${cls} ${animCls}\">", "return `<div class=\"alert-item ${cls} ${animCls}\">")
    
    # Add setTimeout to remove is-new
    remove_is_new_logic = """    seenAlertIds = newSeen;
    setTimeout(() => {
        root.querySelectorAll('.is-new').forEach(el => el.classList.remove('is-new'));
    }, 1500);"""
    js = js.replace("    seenAlertIds = newSeen;", remove_is_new_logic)

    with open('static/dashboard.js', 'w', encoding='utf-8') as f:
        f.write(js)

def inject_helper(filepath):
    import os
    if not os.path.exists(filepath): return
    with open(filepath, 'r', encoding='utf-8') as f:
        js = f.read()
    
    if "function animateCountUp" in js: return

    helper = """
const valueCache = {};
function animateCountUp(el, fromValue, toValue, duration = 400) {
    if (!el) return;
    if (fromValue === toValue) return;

    const parseNum = str => parseFloat(String(str).replace(/[^\\d.-]/g, '')) || 0;
    const getSuffix = str => String(str).replace(/[\\d.-]/g, '').trim();

    const oldNum = parseNum(fromValue);
    const newNum = parseNum(toValue);
    const suffix = getSuffix(toValue);
    const isFloat = String(toValue).includes('.');

    if (oldNum === newNum) {
        el.textContent = toValue;
        return;
    }

    const startTime = performance.now();
    function update(time) {
        const elapsed = time - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const current = oldNum + (newNum - oldNum) * easeOut;
        
        let display = isFloat ? current.toFixed(1) : Math.round(current);
        if (suffix) display += ' ' + suffix;
        el.textContent = display;

        if (progress < 1) requestAnimationFrame(update);
        else el.textContent = toValue;
    }
    requestAnimationFrame(update);
}

function updateElementValue(id, newValue) {
    const el = document.getElementById(id);
    if (!el) return;
    const oldValue = valueCache[id] || el.textContent;
    if (oldValue !== String(newValue)) {
        animateCountUp(el, oldValue, String(newValue));
        valueCache[id] = String(newValue);
    }
}
"""
    js = helper + "\n" + js
    
    # Replace setText or standard innerText assignments
    js = re.sub(r"document\.getElementById\('([^']+)'\)\.textContent = (.*?);", r"updateElementValue('\1', \2);", js)
    # also handle element.textContent = ...
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(js)


def update_html_skeletons():
    # module_predictions.html
    filepath = 'templates/module_predictions.html'
    import os
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
        
        html = html.replace('Waiting for data...', '<div class="skeleton-loader"></div>')
        html = html.replace('Loading...', '<div class="skeleton-loader"></div>')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
            
    # ai_prediction.html
    filepath = 'templates/ai_prediction.html'
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
        html = html.replace('<tr><td colspan="8">Loading model data...</td></tr>', 
                            '<tr><td colspan="8"><div class="skeleton-loader"></div></td></tr>')
        html = html.replace('Weight lock runtime details will appear here.', 
                            '<div class="skeleton-loader" style="height:14px; width:60%"></div>')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)


if __name__ == '__main__':
    update_css()
    update_dashboard_js()
    inject_helper('static/module_predictions.js')
    inject_helper('static/ai_prediction.js')
    update_html_skeletons()
    print("Applied specific 5 UX animations successfully.")
