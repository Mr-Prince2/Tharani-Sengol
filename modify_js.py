import re
import os

def update_dashboard():
    filepath = 'static/dashboard.js'
    with open(filepath, 'r', encoding='utf-8') as f:
        js = f.read()

    # Empty state for alerts
    alerts_old = "root.innerHTML = '<div class=\"alert-item\">No alerts yet.</div>';"
    alerts_new = "root.innerHTML = '<div class=\"empty-state\"><svg xmlns=\"http://www.w3.org/2000/svg\" fill=\"none\" viewBox=\"0 0 24 24\" stroke=\"currentColor\" stroke-width=\"2\"><path stroke-linecap=\"round\" stroke-linejoin=\"round\" d=\"M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z\" /></svg><div>No alerts found.</div></div>';"
    js = js.replace(alerts_old, alerts_new)

    # Empty state for vehicle cards
    veh_old = """    const activeIds = new Set(items.map(item => item.vehicle_id));"""
    veh_new = """    if (!items || !items.length) {
        container.innerHTML = '<div class="empty-state" style="grid-column: 1 / -1;"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg><div>No active vehicles match the current filters.</div></div>';
        return;
    }

    const activeIds = new Set(items.map(item => item.vehicle_id));"""
    js = js.replace(veh_old, veh_new)

    # Chart labeling for dashboard
    chart_old = """        options: {
            responsive: true,
            scales: { y: { min: 0, max: 100 } },
        },"""
    chart_new = """        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top', labels: { color: '#cbd5e1' } },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: {
                x: { 
                    title: { display: true, text: 'Time', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: { 
                    min: 0, max: 100,
                    title: { display: true, text: 'Risk Score (0-100)', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        },"""
    js = js.replace(chart_old, chart_new)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(js)

def update_analytics():
    filepath = 'static/analytics.js'
    with open(filepath, 'r', encoding='utf-8') as f:
        js = f.read()

    # Chart labeling for analytics risk chart
    risk_old = """        options: {
            responsive: true,
            scales: {
                x: { ticks: { maxTicksLimit: 10 } },
                y: { min: 0, max: 100 },
            },
            plugins: { legend: { display: true } },
        },"""
    risk_new = """        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top', labels: { color: '#cbd5e1' } },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: {
                x: { 
                    title: { display: true, text: 'Time', color: '#94a3b8' },
                    ticks: { maxTicksLimit: 10, color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: { 
                    min: 0, max: 100,
                    title: { display: true, text: 'Risk Score (0-100)', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
            },
        },"""
    js = js.replace(risk_old, risk_new)

    # Chart labeling for analytics violation chart
    viol_old = """        options: {
            responsive: true,
            scales: {
                x: { ticks: { maxTicksLimit: 12 } },
                y: { beginAtZero: true },
            },
        },"""
    viol_new = """        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top', labels: { color: '#cbd5e1' } },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: {
                x: { 
                    title: { display: true, text: 'Time', color: '#94a3b8' },
                    ticks: { maxTicksLimit: 12, color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: { 
                    beginAtZero: true,
                    title: { display: true, text: 'Number of Violations', color: '#94a3b8' },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
            },
        },"""
    js = js.replace(viol_old, viol_new)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(js)

if __name__ == '__main__':
    update_dashboard()
    update_analytics()
    print('JS updated.')
