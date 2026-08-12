import re

filepath = 'static/site.css'
with open(filepath, 'r', encoding='utf-8') as f:
    css = f.read()

# 1. Replace alertBlink keyframe and add new keyframes
old_keyframes = """@keyframes alertBlink {
    0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 10px rgba(239, 68, 68, 0.5); }
    50% { opacity: 0.6; transform: scale(0.95); box-shadow: 0 0 20px rgba(239, 68, 68, 0.8); }
}"""

new_keyframes = """@keyframes alertBlink {
    0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 10px rgba(239, 68, 68, 0.5); }
    50% { opacity: 0.6; transform: scale(0.95); box-shadow: 0 0 20px rgba(239, 68, 68, 0.8); }
}

@keyframes slideFadeIn {
    0% { transform: translateY(-10px); background-color: rgba(37, 99, 235, 0.4); opacity: 0; }
    20% { transform: translateY(0); opacity: 1; }
    100% { background-color: rgba(37, 99, 235, 0.05); opacity: 1; }
}

@keyframes pulseCritical {
    0% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.8; transform: scale(0.98); }
    100% { opacity: 1; transform: scale(1); }
}

@keyframes shimmer {
    0% { background-position: -1000px 0; }
    100% { background-position: 1000px 0; }
}

@keyframes fadeInLayer {
    from { opacity: 0; }
    to { opacity: 1; }
}

.new-alert {
    animation: slideFadeIn 2s ease-out forwards;
}

.skeleton-loader {
    animation: shimmer 2s infinite linear;
    background: linear-gradient(90deg, rgba(255,255,255,0.02) 8%, rgba(255,255,255,0.06) 18%, rgba(255,255,255,0.02) 33%);
    background-size: 1000px 100%;
    border-radius: 6px;
    height: 100%;
    width: 100%;
}
.skeleton-text { height: 16px; margin: 4px 0; border-radius: 4px; }
.skeleton-title { height: 24px; margin-bottom: 12px; border-radius: 4px; }
.skeleton-block { height: 60px; border-radius: 8px; }

.leaflet-heatmap-layer, .leaflet-overlay-pane path {
    animation: fadeInLayer 0.5s ease-out;
}
"""
if "@keyframes slideFadeIn" not in css:
    css = css.replace(old_keyframes, new_keyframes)

# 2. Add badge pulse to danger and suspicious
old_danger = """.badge.danger {
    background: rgba(239, 68, 68, 0.15);
    color: var(--status-danger);
    border: 1px solid rgba(239, 68, 68, 0.4);
    animation: alertBlink 1.5s infinite;
}"""
new_danger = """.badge.danger {
    background: rgba(239, 68, 68, 0.15);
    color: var(--status-danger);
    border: 1px solid rgba(239, 68, 68, 0.4);
    animation: pulseCritical 2s infinite ease-in-out;
}"""
css = css.replace(old_danger, new_danger)

old_sus = """.badge.suspicious {
    background: rgba(245, 158, 11, 0.15);
    color: var(--status-warning);
    border: 1px solid rgba(245, 158, 11, 0.4);
}"""
new_sus = """.badge.suspicious {
    background: rgba(245, 158, 11, 0.15);
    color: var(--status-warning);
    border: 1px solid rgba(245, 158, 11, 0.4);
    animation: pulseCritical 2s infinite ease-in-out;
}"""
css = css.replace(old_sus, new_sus)

# 3. Add active states to buttons
old_btn_active = "transition: all 0.2s ease;"
new_btn_active = """transition: all 0.2s ease;
}
.btn-link:active, button:active, .page-chip:active {
    transform: scale(0.97);"""

# Just append to the end of the file since it's safer
css += """
.btn-link:active, button:active, .page-chip:active, .district-pill:active {
    transform: scale(0.97);
}
"""

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(css)

print("CSS updated for animations.")
