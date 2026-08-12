import re

def update_dashboard():
    with open('static/dashboard.js', 'r', encoding='utf-8') as f:
        js = f.read()

    # 1. Add animateValue, attachButtonFeedback, slideMarker, and seenAlertIds
    helpers = """const valueCache = {};
function animateValue(id, newValue, duration = 400) {
    const el = document.getElementById(id);
    if (!el) return;
    
    if (valueCache[id] === newValue) return;
    const oldRaw = valueCache[id] || '0';
    valueCache[id] = newValue;

    const parseNum = str => parseFloat(String(str).replace(/[^\\d.-]/g, '')) || 0;
    const getSuffix = str => String(str).replace(/[\\d.-]/g, '').trim();

    const oldNum = parseNum(oldRaw);
    const newNum = parseNum(newValue);
    const suffix = getSuffix(newValue);
    const isFloat = String(newValue).includes('.');

    if (oldNum === newNum) {
        el.textContent = newValue;
        return;
    }

    const startTime = performance.now();
    function update(time) {
        const elapsed = time - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const current = oldNum + (newNum - oldNum) * progress;
        
        let display = isFloat ? current.toFixed(1) : Math.round(current);
        if (suffix) display += ' ' + suffix;
        el.textContent = display;

        if (progress < 1) requestAnimationFrame(update);
        else el.textContent = newValue;
    }
    requestAnimationFrame(update);
}

function attachButtonFeedback(btnId) {
    const btn = document.getElementById(btnId);
    if (!btn || btn.dataset.feedbackBound) return;
    btn.dataset.feedbackBound = '1';
    btn.addEventListener('click', () => {
        const originalText = btn.innerHTML;
        btn.innerHTML = '✓ Done';
        setTimeout(() => { btn.innerHTML = originalText; }, 1000);
    });
}

function slideMarker(marker, targetLatLng, duration=1000) {
    const startLatLng = marker.getLatLng();
    const startTime = performance.now();
    function update(time) {
        const elapsed = time - startTime;
        const p = Math.min(elapsed / duration, 1);
        const easeOut = 1 - Math.pow(1 - p, 3);
        const lat = startLatLng.lat + (targetLatLng[0] - startLatLng.lat) * easeOut;
        const lng = startLatLng.lng + (targetLatLng[1] - startLatLng.lng) * easeOut;
        marker.setLatLng([lat, lng]);
        if (p < 1) requestAnimationFrame(update);
        else marker.setLatLng(targetLatLng);
    }
    requestAnimationFrame(update);
}

let seenAlertIds = new Set();
let isFirstRiskChartRender = true;
"""
    if "function animateValue" not in js:
        js = js.replace("const map = L.map('map').setView([10.816, 78.730], 8);", helpers + "\nconst map = L.map('map').setView([10.816, 78.730], 8);")

    # 2. Update setText to animateValue for KPIs
    js = js.replace("setText('vehicleCount'", "animateValue('vehicleCount'")
    js = js.replace("setText('tripCount'", "animateValue('tripCount'")
    js = js.replace("setText('dangerCount'", "animateValue('dangerCount'")
    js = js.replace("setText('suspiciousCount'", "animateValue('suspiciousCount'")
    js = js.replace("setText('stackClassVehicles'", "animateValue('stackClassVehicles'")
    js = js.replace("setText('stackClassHigh'", "animateValue('stackClassHigh'")
    js = js.replace("setText('stackClassMedium'", "animateValue('stackClassMedium'")
    js = js.replace("setText('stackClassProb'", "animateValue('stackClassProb'")
    js = js.replace("setText('stackRegLocked'", "animateValue('stackRegLocked'")
    js = js.replace("setText('stackRegOverload'", "animateValue('stackRegOverload'")
    js = js.replace("setText('stackRegAvgWeight'", "animateValue('stackRegAvgWeight'")
    js = js.replace("setText('stackSystemScale'", "animateValue('stackSystemScale'")
    js = js.replace("setText('tnConfiguredTrucks'", "animateValue('tnConfiguredTrucks'")
    js = js.replace("setText('tnConfiguredRoutes'", "animateValue('tnConfiguredRoutes'")
    js = js.replace("setText('tnConfiguredMines'", "animateValue('tnConfiguredMines'")
    js = js.replace("setText('tnActiveTrucks'", "animateValue('tnActiveTrucks'")
    js = js.replace("setText('tnOverloads'", "animateValue('tnOverloads'")
    js = js.replace("setText('tnAvgRisk'", "animateValue('tnAvgRisk'")
    js = js.replace("setText('tnAvgThreat'", "animateValue('tnAvgThreat'")

    # 3. renderAlerts
    old_alerts = """    root.innerHTML = alerts.slice(0, 12).map(item => {
        const cls = item.severity === 'critical' ? 'critical' : '';
        return `<div class="alert-item ${cls}"><strong>${item.vehicle_id}</strong> ${item.message}<br>${formatTs(item.time)}</div>`;
    }).join('');"""
    
    new_alerts = """    const newSeen = new Set();
    root.innerHTML = alerts.slice(0, 12).map(item => {
        const idKey = item.vehicle_id + item.time;
        newSeen.add(idKey);
        const isNew = !seenAlertIds.has(idKey) && seenAlertIds.size > 0;
        const cls = item.severity === 'critical' ? 'critical' : '';
        const animCls = isNew ? 'new-alert' : '';
        return `<div class="alert-item ${cls} ${animCls}"><strong>${item.vehicle_id}</strong> ${item.message}<br>${formatTs(item.time)}</div>`;
    }).join('');
    seenAlertIds = newSeen;"""
    if "const newSeen = new Set();" not in js:
        js = js.replace(old_alerts, new_alerts)

    # 4. Marker Interpolation
    old_marker = """            } else {
                markers[item.vehicle_id].setLatLng(position);
                markers[item.vehicle_id].setStyle({ color: style.color, fillColor: style.color });
            }"""
    new_marker = """            } else {
                slideMarker(markers[item.vehicle_id], position);
                markers[item.vehicle_id].setStyle({ color: style.color, fillColor: style.color });
            }"""
    js = js.replace(old_marker, new_marker)

    # 5. Chart Draw-in
    old_chart = """        options: {
            responsive: true,"""
    new_chart = """        options: {
            animation: isFirstRiskChartRender ? { duration: 1000, easing: 'easeOutQuart' } : false,
            responsive: true,"""
    if "isFirstRiskChartRender ?" not in js:
        js = js.replace(old_chart, new_chart)
        js = js.replace("historyChart = new Chart(", "isFirstRiskChartRender = false;\n    historyChart = new Chart(")

    # 6. Global Button Feedback
    btn_feedback = """
document.querySelectorAll('a[href^="/export/"]').forEach(a => {
    if (a.dataset.feedbackBound) return;
    a.dataset.feedbackBound = '1';
    a.addEventListener('click', function() {
        const original = this.innerHTML;
        this.innerHTML = '✓ Exporting...';
        setTimeout(() => this.innerHTML = original, 1500);
    });
});
attachButtonFeedback('singleLorrySearchBtn');
attachButtonFeedback('singleLorryClearBtn');
attachButtonFeedback('searchApplyBtn');
attachButtonFeedback('searchClearBtn');
"""
    if "✓ Exporting" not in js:
        js += btn_feedback

    with open('static/dashboard.js', 'w', encoding='utf-8') as f:
        f.write(js)

def update_analytics():
    with open('static/analytics.js', 'r', encoding='utf-8') as f:
        js = f.read()
    
    # 5. Chart Draw-in
    old_opt = """        options: {
            responsive: true,"""
    new_opt = """        options: {
            animation: isFirstRiskChartRender ? { duration: 1000, easing: 'easeOutQuart' } : false,
            responsive: true,"""
    if "isFirstRiskChartRender ?" not in js:
        js = "let isFirstRiskChartRender = true;\n" + js
        js = js.replace(old_opt, new_opt)
        js = js.replace("riskChart = new Chart(", "isFirstRiskChartRender = false;\n    riskChart = new Chart(")
        js = js.replace("violationChart = new Chart(", "isFirstRiskChartRender = false;\n    violationChart = new Chart(")

    with open('static/analytics.js', 'w', encoding='utf-8') as f:
        f.write(js)

def update_vehicles():
    with open('static/vehicles.js', 'r', encoding='utf-8') as f:
        js = f.read()

    btn_feedback = """
function attachButtonFeedback(btnId) {
    const btn = document.getElementById(btnId);
    if (!btn || btn.dataset.feedbackBound) return;
    btn.dataset.feedbackBound = '1';
    btn.addEventListener('click', () => {
        const originalText = btn.innerHTML;
        btn.innerHTML = '✓ Done';
        setTimeout(() => { btn.innerHTML = originalText; }, 1000);
    });
}
attachButtonFeedback('vehiclesSearchApplyBtn');
attachButtonFeedback('vehiclesSearchClearBtn');
"""
    if "attachButtonFeedback" not in js:
        js += btn_feedback
    
    with open('static/vehicles.js', 'w', encoding='utf-8') as f:
        f.write(js)


if __name__ == '__main__':
    update_dashboard()
    update_analytics()
    update_vehicles()
    print('JS animations applied.')
