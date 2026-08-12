import re
import os

filepath = 'd:/COLLEGE/Tharanai Sengol/Tharani-Sengol/static/site.css'
with open(filepath, 'r', encoding='utf-8') as f:
    css = f.read()

# 1. Update variables
vars_old = """    /* Dark Theme Surface Colors */
    --bg-dark: #040711;
    --bg-card: rgba(13, 20, 38, 0.75);
    --bg-card-hover: rgba(18, 28, 54, 0.88);
    --bg-surface: rgba(15, 23, 42, 0.85);
    --bg-input: rgba(10, 16, 30, 0.88);
    
    /* Vibrant Accents */
    --accent-cyan: #38bdf8;
    --accent-cyan-glow: rgba(56, 189, 248, 0.3);
    --accent-blue: #2563eb;
    --accent-indigo: #6366f1;
    --accent-emerald: #10b981;
    --accent-amber: #f59e0b;
    --accent-rose: #ef4444;
    
    /* Typography Colors */
    --text-primary: #f8fafc;
    --text-secondary: #cbd5e1;
    --text-muted: #94a3b8;
    --text-dim: #64748b;
    
    /* Borders & Depth Shadows */
    --border-subtle: rgba(255, 255, 255, 0.08);
    --border-accent: rgba(56, 189, 248, 0.24);
    --border-focus: #0ea5e9;
    --card-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.6), 0 0 30px rgba(14, 165, 233, 0.05);
    --hover-shadow: 0 30px 60px -12px rgba(0, 0, 0, 0.75), 0 0 35px rgba(56, 189, 248, 0.2);"""

vars_new = """    /* Strict Color System */
    --bg-dark: #060913;
    --bg-sidebar: #0a0f1e;
    --bg-card: rgba(15, 23, 42, 0.75);
    --bg-card-hover: rgba(22, 33, 60, 0.88);
    --bg-surface: rgba(15, 23, 42, 0.85);
    --bg-input: rgba(10, 15, 30, 0.88);
    
    /* Primary Brand */
    --brand-primary: #2563eb;
    --brand-primary-glow: rgba(37, 99, 235, 0.3);
    --accent-cyan: #38bdf8;
    --accent-blue: #2563eb;
    
    /* Semantic Status (Strictly reserved) */
    --status-safe: #10b981;
    --status-warning: #f59e0b;
    --status-danger: #ef4444;
    
    /* Typography Colors */
    --text-primary: #f8fafc;
    --text-secondary: #cbd5e1;
    --text-muted: #94a3b8;
    --text-dim: #64748b;
    
    /* Typography Scale */
    --text-kpi: 32px;
    --text-h2: 24px;
    --text-body: 16px;
    --text-meta: 13px;
    
    /* Borders & Depth */
    --border-subtle: rgba(255, 255, 255, 0.08);
    --border-accent: rgba(37, 99, 235, 0.24);
    --border-focus: #3b82f6;
    --card-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    --hover-shadow: 0 20px 40px -12px rgba(0, 0, 0, 0.6);"""
css = css.replace(vars_old, vars_new)

# 2. Typography
typo_old = """h1 { font-size: 2.1rem; font-weight: 800; }
h2 { font-size: 1.45rem; font-weight: 700; }
h3 { font-size: 1.2rem; font-weight: 600; }
h4 { font-size: 1rem; font-weight: 600; }"""
typo_new = """h1 { font-size: 2.1rem; font-weight: 800; }
h2 { font-size: var(--text-h2); font-weight: 700; }
h3 { font-size: 1.2rem; font-weight: 600; }
h4 { font-size: 1rem; font-weight: 600; }"""
css = css.replace(typo_old, typo_new)

# 3. Header replacement
header_re = re.compile(r'/\* Sticky Top Header & Responsive Navbar \*/.*?/\* Main Content Container \*/', re.DOTALL)
new_layout = """/* App Layout & Sidebar */
.app-layout {
    display: flex;
    min-height: 100vh;
    width: 100%;
}

.main-content {
    flex: 1;
    margin-left: 260px;
    width: calc(100% - 260px);
    transition: margin-left 0.3s ease, width 0.3s ease;
}

/* Sidebar Styling */
.sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: 260px;
    height: 100vh;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border-accent);
    display: flex;
    flex-direction: column;
    z-index: 1000;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 5px 0 25px rgba(0, 0, 0, 0.5);
}

.sidebar-header {
    padding: 24px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border-subtle);
}

.brand-wrap {
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
    transition: transform 0.2s ease;
}
.brand-wrap:hover { transform: scale(1.02); }

.brand-emblem {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.2), rgba(56, 189, 248, 0.15));
    border: 1px solid rgba(56, 189, 248, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--accent-cyan);
    box-shadow: 0 0 15px rgba(37, 99, 235, 0.2);
    flex-shrink: 0;
}
.brand-emblem svg { width: 20px; height: 20px; }

.brand-text-container {
    display: flex;
    flex-direction: column;
}
.brand-text-container h1 {
    font-size: 1.1rem;
    font-weight: 800;
    margin: 0;
    background: linear-gradient(135deg, #ffffff 40%, #93c5fd 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.brand-text-container p {
    margin: 0;
    font-size: var(--text-meta);
    color: var(--text-muted);
    font-weight: 500;
}

.close-sidebar-btn {
    display: none;
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 1.8rem;
    cursor: pointer;
    line-height: 1;
}

nav {
    flex: 1;
    overflow-y: auto;
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

nav a {
    text-decoration: none;
    color: var(--text-secondary);
    padding: 10px 16px;
    border-radius: 8px;
    font-size: var(--text-meta);
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 12px;
    transition: all 0.2s ease;
    border: 1px solid transparent;
}

nav a:hover {
    background: rgba(255, 255, 255, 0.04);
    color: #ffffff;
}

nav a.active {
    background: rgba(37, 99, 235, 0.15);
    color: var(--accent-cyan);
    border: 1px solid rgba(37, 99, 235, 0.3);
}

.sidebar-footer {
    padding: 20px;
    border-top: 1px solid var(--border-subtle);
    display: flex;
    flex-direction: column;
    gap: 12px;
}

#authUserBadge {
    font-size: var(--text-meta);
    font-weight: 600;
    color: var(--status-safe);
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.2);
    padding: 6px 12px;
    border-radius: 12px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
#authUserBadge::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: var(--status-safe);
    box-shadow: 0 0 8px var(--status-safe);
    animation: alertBlink 2s infinite ease-in-out;
}

.mobile-top-bar {
    display: none;
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(6, 11, 24, 0.95);
    border-bottom: 1px solid var(--border-accent);
    padding: 12px 20px;
    justify-content: space-between;
    align-items: center;
    backdrop-filter: blur(10px);
}
.mobile-top-bar .brand-wrap h1 {
    font-size: 1.1rem;
    font-weight: 800;
    margin: 0;
    background: linear-gradient(135deg, #ffffff 40%, #93c5fd 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.mobile-menu-btn {
    background: rgba(37, 99, 235, 0.15);
    border: 1px solid rgba(37, 99, 235, 0.3);
    color: var(--accent-cyan);
    padding: 6px 10px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* Main Content Container */"""
css = header_re.sub(new_layout, css)

# 4. Mobile Breakpoints
mobile_re = re.compile(r'@media \(max-width: 992px\) \{.*?\n\}', re.DOTALL)
new_mobile = """@media (max-width: 992px) {
    .sidebar {
        transform: translateX(-100%);
    }
    .sidebar.mobile-open {
        transform: translateX(0);
    }
    .main-content {
        margin-left: 0;
        width: 100%;
    }
    .mobile-top-bar {
        display: flex;
    }
    .close-sidebar-btn {
        display: block;
    }
    .grid.two, .vehicle-grid, .summary-grid {
        grid-template-columns: 1fr;
    }
}"""
css = mobile_re.sub(new_mobile, css)

# 5. Table Scannability
table_re = re.compile(r'/\* Mobile-Friendly Touch Responsive Table System \*/.*?/\* Touch-Friendly Inputs, Selects, Buttons \*/', re.DOTALL)
new_table = """/* High-Scannability Data Tables */
.table-responsive {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    border-radius: 12px;
    border: 1px solid var(--border-subtle);
    margin: 16px 0;
    background: rgba(10, 15, 30, 0.5);
}

table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: var(--text-meta);
    color: var(--text-primary);
    white-space: nowrap;
}

th, td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border-subtle);
}

th {
    color: var(--text-muted);
    font-weight: 600;
    background: rgba(15, 23, 42, 0.95);
    font-family: var(--font-sans);
    letter-spacing: 0.5px;
    text-transform: uppercase;
    font-size: 0.75rem;
    position: sticky;
    top: 0;
    z-index: 10;
}

tr:nth-child(even) td {
    background: rgba(255, 255, 255, 0.02);
}

tr:hover td {
    background: rgba(37, 99, 235, 0.08);
}

.link-inline {
    color: var(--brand-secondary);
    text-decoration: none;
    font-weight: 600;
    transition: color 0.2s ease;
}

.link-inline:hover {
    color: #93c5fd;
    text-decoration: underline;
}

/* Empty & Loading States */
.empty-state {
    padding: 40px 20px;
    text-align: center;
    color: var(--text-muted);
    font-size: var(--text-meta);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    border: 1px dashed var(--border-subtle);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.02);
}
.empty-state svg {
    width: 42px;
    height: 42px;
    opacity: 0.5;
    color: var(--text-dim);
}

/* Touch-Friendly Inputs, Selects, Buttons */"""
css = table_re.sub(new_table, css)

# 6. KPI Strong typography
kpi_re = re.compile(r'\.summary-grid strong \{.*?\n\}', re.DOTALL)
new_kpi = """.summary-grid strong {
    display: block;
    margin-top: 10px;
    font-size: var(--text-kpi);
    font-family: var(--font-heading);
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.5px;
}"""
css = kpi_re.sub(new_kpi, css)

# Update colors for vehicles and alerts
css = css.replace("var(--accent-emerald)", "var(--status-safe)")
css = css.replace("var(--accent-rose)", "var(--status-danger)")

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(css)

print("Updated site.css layout, typography and colors.")
