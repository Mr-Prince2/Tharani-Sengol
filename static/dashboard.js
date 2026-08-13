const valueCache = {};
function animateCountUp(id, newValue, duration = 400) {
    const el = document.getElementById(id);
    if (!el) return;
    
    if (valueCache[id] === newValue) return;
    const oldRaw = valueCache[id] || '0';
    valueCache[id] = newValue;

    const parseNum = str => parseFloat(String(str).replace(/[^\d.-]/g, '')) || 0;
    const getSuffix = str => String(str).replace(/[\d.-]/g, '').trim();

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

const map = L.map('map', {
    zoomControl: true,
    scrollWheelZoom: true,
    maxZoom: 19
}).setView([10.816, 78.730], 8);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19
}).addTo(map);

// Invalidate Leaflet viewport size to fix container layout clipping
setTimeout(() => { map.invalidateSize(); }, 150);
setTimeout(() => { map.invalidateSize(); }, 600);
setTimeout(() => { map.invalidateSize(); }, 1500);
window.addEventListener('resize', () => { map.invalidateSize(); });

let markers = {};
let heatLayer = null;
let routeLayers = [];
let historyChart = null;
let selectedLorry = null;
let dashboardRefreshInFlight = false;
let dashboardRefreshQueued = false;
let lastRouteSignature = '';
let dashboardState = {
    query: '',
    district: '',
    page: 1,
    pageSize: 20,
};

const explainModal = document.getElementById('riskExplainModal');
const closeExplainBtn = document.getElementById('closeExplainBtn');
if (closeExplainBtn) {
    closeExplainBtn.addEventListener('click', () => explainModal.close());
}

function riskStyle(risk) {
    if (risk >= 80) return { color: '#ff0055', cls: 'danger', label: 'Risky Vehicle' };
    if (risk >= 50) return { color: '#ffb703', cls: 'suspicious', label: 'Suspicious Activity' };
    return { color: '#10b981', cls: 'safe', label: 'Authorized Vehicle' };
}

function formatPredictionLabel(label) {
    const labelMap = {
        low: 'Low Risk',
        medium: 'Moderate Risk',
        high: 'High Risk',
        sus: 'Suspicious Activity',
        suspicious: 'Suspicious Activity',
        imposter: 'Risky Vehicle',
        impostor: 'Risky Vehicle',
        crewmate: 'Authorized Vehicle',
        normal: 'Normal',
    };

    const raw = String(label || 'LOW');
    return raw
        .split(',')
        .map(part => part.trim())
        .filter(Boolean)
        .map(part => {
            const key = part.toLowerCase();
            if (labelMap[key]) return labelMap[key];
            return part
                .replace(/_/g, ' ')
                .toLowerCase()
                .replace(/\b\w/g, char => char.toUpperCase());
        })
        .join(', ');
}

function formatTs(value) {
    if (!value) return 'n/a';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString();
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setMapCenterFromDistrict(district) {
    const mapCenters = {
        'chennai': [13.0827, 80.2707],
        'coimbatore': [11.0168, 76.9558],
        'madurai': [9.9252, 78.1198],
        'tiruchirappalli': [10.7905, 78.7047],
        'salem': [11.6643, 78.1460],
        'tirunelveli': [8.7139, 77.7567],
        'erode': [11.341, 77.7172],
        'vellore': [12.9165, 79.1325],
        'thoothukudi': [8.7642, 78.1348],
        'thanjavur': [10.7867, 79.1378],
        'dindigul': [10.3673, 77.9803],
        'villupuram': [11.9426, 79.4977],
        'kancheepuram': [12.8342, 79.7036],
        'namakkal': [11.2189, 78.1674],
        'karur': [10.9601, 78.0766],
        'cuddalore': [11.7480, 79.7714],
        'ramanathapuram': [9.3706, 78.8335],
        'sivaganga': [9.8470, 78.4800],
        'virudhunagar': [9.5680, 77.9624],
        'kanyakumari': [8.0883, 77.5385],
    };
    if (!district) {
        map.setView([10.816, 78.730], 8);
        return;
    }
    const target = mapCenters[district.toLowerCase()];
    if (target) map.setView(target, 10);
}

function paintHeatmap(points) {
    const heat = points.map(p => [p.lat, p.lon, Number(p.weight || 1)]);
    if (!heatLayer) {
        heatLayer = L.heatLayer(heat, { radius: 22, blur: 18, minOpacity: 0.2 }).addTo(map);
        return;
    }
    heatLayer.setLatLngs(heat);
}

function renderAlerts(alerts) {
    const root = document.getElementById('alertFeed');
    if (!root) return;
    if (!alerts.length) {
        root.innerHTML = '<div class="empty-state"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg><div>No alerts found.</div></div>';
        return;
    }
    const newSeen = new Set();
    root.innerHTML = alerts.slice(0, 12).map(item => {
        const idKey = item.vehicle_id + item.time;
        newSeen.add(idKey);
        const isNew = !seenAlertIds.has(idKey) && seenAlertIds.size > 0;
        const cls = item.severity === 'critical' ? 'critical' : '';
        const animCls = isNew ? 'is-new' : '';
        return `<div class="alert-item ${cls} ${animCls}"><strong>${item.vehicle_id}</strong> ${item.message}<br>${formatTs(item.time)}</div>`;
    }).join('');
    seenAlertIds = newSeen;
    setTimeout(() => {
        root.querySelectorAll('.is-new').forEach(el => el.classList.remove('is-new'));
    }, 1500);
}

async function showRiskExplain(vehicleId) {
    const response = await fetch(`/api/vehicle/${vehicleId}/explain`);
    const details = await response.json();
    const probPct = Math.round((details.prediction?.probability || 0) * 100);
    const weightVal = Number(details.weight_prediction?.predicted_weight || 0).toFixed(1);
    const isOverload = Boolean(details.weight_prediction?.overload_flag);

    document.getElementById('explainTitle').textContent = `${vehicleId} XAI Risk Analysis`;
    document.getElementById('explainSummary').innerHTML = `
        <div class="xai-card">
            <div class="xai-header">
                <strong>ML Confidence Score: ${probPct}% (${details.risk_level})</strong>
                <span class="badge ${details.risk >= 80 ? 'danger' : (details.risk >= 50 ? 'suspicious' : 'safe')}"><span class="badge-dot"></span>Risk ${details.risk}</span>
            </div>
            <div class="xai-progress-track">
                <div class="xai-progress-bar" style="width: ${probPct}%; background: ${details.risk >= 80 ? '#ef4444' : (details.risk >= 50 ? '#f59e0b' : '#10b981')}"></div>
            </div>
            <p style="margin-bottom:10px; font-size:0.88rem;"><strong>Load Assessment:</strong> Estimated ${weightVal} tons (Allowed: 20.0 tons) — ${isOverload ? '🔴 Overload Flagged' : '🟢 Within Permit Threshold'}.</p>
        </div>
    `;
    document.getElementById('heatHelp').textContent = details.how_heatmap_works;

    const riskList = document.getElementById('riskReasonsList');
    const safeList = document.getElementById('safeReasonsList');
    riskList.innerHTML = (details.risk_reasons || []).map(item => `<li class="xai-factor-item"><span>${item.reason} (+${item.points} pts) at ${formatTs(item.time)}</span></li>`).join('') || '<li class="xai-factor-item"><span>No critical risk triggers detected</span></li>';
    safeList.innerHTML = (details.safe_reasons || []).map(item => `<li class="xai-factor-item"><span>${item}</span></li>`).join('') || '<li class="xai-factor-item"><span>Standard fleet baseline</span></li>';
    explainModal.showModal();
}

function renderPageControls(meta, onPageChange) {
    const root = document.getElementById('lorryPageControls');
    if (!root) return;
    const totalPages = Number(meta.total_pages || 1);
    const page = Number(meta.page || 1);

    const pages = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);
    for (let index = start; index <= end; index += 1) {
        pages.push(`<button class="page-chip ${index === page ? 'active' : ''}" data-page="${index}" type="button">${index}</button>`);
    }

    root.innerHTML = `
        <button class="page-chip" data-nav="prev" type="button" ${page <= 1 ? 'disabled' : ''}>Prev</button>
        ${pages.join('')}
        <button class="page-chip" data-nav="next" type="button" ${page >= totalPages ? 'disabled' : ''}>Next</button>
        <span class="muted">Page ${page} of ${totalPages} | ${meta.total || 0} trucks</span>
    `;

    root.querySelectorAll('[data-page]').forEach(btn => {
        btn.addEventListener('click', () => onPageChange(Number(btn.getAttribute('data-page'))));
    });
    root.querySelectorAll('[data-nav]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.getAttribute('data-nav') === 'prev') onPageChange(Math.max(1, page - 1));
            if (btn.getAttribute('data-nav') === 'next') onPageChange(Math.min(totalPages, page + 1));
        });
    });
}

function renderDistrictPills(districts) {
    const root = document.getElementById('districtPills');
    const select = document.getElementById('districtFilterSelect');
    if (!root && !select) return;

    const items = [{ district: '', label: 'All Districts' }, ...(districts || []).map(item => ({ district: item.district, label: item.district }))];

    if (root) {
        root.innerHTML = items.map(item => `<button class="district-pill ${dashboardState.district === item.district ? 'active' : ''}" data-district="${item.district}" type="button">${item.label}</button>`).join('');
        root.querySelectorAll('[data-district]').forEach(btn => {
            btn.addEventListener('click', () => {
                dashboardState.district = btn.getAttribute('data-district') || '';
                dashboardState.page = 1;
                refresh();
            });
        });
    }

    if (select) {
        const previous = select.value;
        select.innerHTML = items.map(item => `<option value="${item.district}">${item.label}</option>`).join('');
        select.value = dashboardState.district || previous || '';
    }
}

function renderVehicleCards(items) {
    const container = document.getElementById('vehicleCards');
    if (!container) return;

    if (!items || !items.length) {
        container.innerHTML = '<div class="empty-state" style="grid-column: 1 / -1;"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg><div>No active vehicles match the current filters.</div></div>';
        return;
    }

    const activeIds = new Set(items.map(item => item.vehicle_id));
    Object.keys(markers).forEach(vehicleId => {
        if (!activeIds.has(vehicleId)) {
            map.removeLayer(markers[vehicleId]);
            delete markers[vehicleId];
        }
    });

    container.innerHTML = items.map(item => {
        const prediction = item.prediction || { label: item.prediction_label || 'LOW', probability: item.prediction_probability || 0, reason: item.last_event || 'n/a' };
        const predictionLabel = formatPredictionLabel(prediction.label);
        const risk = Number(item.risk || 0);
        const weight = Number(item.predicted_weight || 0);
        const averageWeight = Number(item.average_weight || 0);
        const weightLocked = Boolean(item.weight_locked);
        const overload = Boolean(item.overload_flag);
        const style = riskStyle(risk);
        const zone = item.zone_name || item.current_zone_name || 'Outside';
        const profile = item.profile || 'normal';
        const position = item.lat && item.lon ? [item.lat, item.lon] : null;
        const isCritical = risk >= 80 || overload;
        const isSuspicious = risk >= 50 && risk < 80;

        if (position) {
            const markerRadius = isCritical ? 8 : (isSuspicious ? 6 : 4);
            const markerOpacity = isCritical ? 0.95 : (isSuspicious ? 0.8 : 0.6);
            const markerWeight = isCritical ? 2 : 1;

            if (!markers[item.vehicle_id]) {
                markers[item.vehicle_id] = L.circleMarker(position, {
                    radius: markerRadius,
                    color: style.color,
                    fillColor: style.color,
                    fillOpacity: markerOpacity,
                    weight: markerWeight,
                    className: isCritical ? 'pulse-marker-ring' : '',
                }).addTo(map);
            } else {
                slideMarker(markers[item.vehicle_id], position);
                markers[item.vehicle_id].setStyle({
                    radius: markerRadius,
                    color: style.color,
                    fillColor: style.color,
                    fillOpacity: markerOpacity,
                    weight: markerWeight
                });
            }
            markers[item.vehicle_id].bindPopup(`
                <div style="font-family:var(--font-sans); padding:4px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <strong style="font-family:var(--font-heading); font-size:1.05rem;">${item.vehicle_id}</strong>
                        <span class="badge ${style.cls}"><span class="badge-dot"></span>${style.label}</span>
                    </div>
                    <div style="font-size:0.82rem; color:#64748b; line-height:1.5;">
                        District: <strong>${item.district || 'Unknown'}</strong><br>
                        Material Profile: <strong>${profile}</strong><br>
                        Current Load: <strong>${weight.toFixed(1)} tons</strong> (Limit: 20.0t)<br>
                        Overload Flag: <strong style="color:${overload ? '#ef4444' : '#10b981'}">${overload ? '🔴 YES' : '🟢 NO'}</strong><br>
                        Zone Location: ${zone}
                    </div>
                </div>
            `);
        }

        return `
            <article class="vehicle-card" style="border-left-color:${style.color}">
                <div style="display:flex; align-items:center; justify-content:space-between;">
                    <h3 style="font-family:var(--font-heading);">${item.vehicle_id}</h3>
                    <span class="badge ${style.cls}" data-vehicle-id="${item.vehicle_id}"><span class="badge-dot"></span>${style.label} • ${risk.toFixed(1)}</span>
                </div>
                <div class="vehicle-meta">
                    District: <strong>${item.district || 'Unknown'}</strong><br>
                    Profile: <strong>${profile}</strong><br>
                    Route: ${item.route_name || item.route_id || '-'}<br>
                    Zone: ${zone}<br>
                    Trips: ${item.trips || 0} total / ${item.trips_24h || 0} in 24h<br>
                    Weight: <strong>${weight.toFixed(1)} tons</strong> ${weightLocked ? '(Locked)' : '(Real-time)'}<br>
                    Overload: <strong style="color:${overload ? 'var(--accent-rose)' : 'var(--accent-emerald)'}">${overload ? '🔴 YES' : '🟢 NO'}</strong><br>
                    Threat Score: <strong>${Number(item.final_threat_score || 0).toFixed(1)}</strong>
                </div>
                <div style="margin-top:8px; display:flex; gap:8px;">
                    <button type="button" class="btn-link" style="font-size:0.78rem; padding:4px 10px;" onclick="showRiskExplain('${item.vehicle_id}')">XAI Explain</button>
                    <a class="btn-link" style="font-size:0.78rem; padding:4px 10px;" href="/vehicles/${encodeURIComponent(item.vehicle_id)}">Full Log</a>
                </div>
            </article>
        `;
    }).join('');

    container.querySelectorAll('.badge[data-vehicle-id]').forEach(el => {
        el.addEventListener('click', () => showRiskExplain(el.getAttribute('data-vehicle-id')));
    });
}

function renderRiskChart(historyData) {
    const canvas = document.getElementById('riskHistoryChart');
    if (!canvas) return;

    const labelsSet = new Set();
    Object.values(historyData).forEach(points => {
        points.slice(-30).forEach(point => labelsSet.add(formatTs(point.ts)));
    });
    const labels = Array.from(labelsSet).slice(-30);

    const palette = ['#1a73e8', '#d93025', '#f9ab00', '#188038', '#7baaf7', '#f28b82'];
    const datasets = Object.entries(historyData).map(([vehicleId, points], index) => {
        const mapValues = new Map(points.slice(-40).map(point => [formatTs(point.ts), Number(point.risk || 0)]));
        return {
            label: vehicleId,
            data: labels.map(label => mapValues.has(label) ? mapValues.get(label) : null),
            borderColor: palette[index % palette.length],
            backgroundColor: palette[index % palette.length],
            spanGaps: true,
            tension: 0.25,
            pointRadius: 0,
        };
    });

    if (historyChart) {
        historyChart.destroy();
    }

    isFirstRiskChartRender = false;
    historyChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            animation: isFirstRiskChartRender ? { duration: 1000, easing: 'easeOutQuart' } : false,
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
        },
    });
}

async function refreshMapContext() {
    const response = await fetch(`/api/map-context?district=${encodeURIComponent(dashboardState.district || '')}&page=${dashboardState.page}&page_size=${dashboardState.pageSize}&query=${encodeURIComponent(dashboardState.query || '')}&heat_limit=400`);
    return response.json();
}

function normalizeVehicleSearch(input) {
    const raw = String(input || '').trim().toLowerCase();
    if (!raw) return '';
    const numeric = raw.match(/\d{1,4}/);
    if (raw.startsWith('truck_')) return raw;
    if (raw.startsWith('truck-')) return raw.replace('truck-', 'truck_');
    if (numeric) return `truck_${Number(numeric[0])}`;
    return raw;
}

async function resolveVehicleId(searchValue, district = '') {
    const normalized = normalizeVehicleSearch(searchValue);
    if (!normalized) return '';

    try {
        const directRes = await fetch(`/api/vehicle/${encodeURIComponent(normalized)}/detail`);
        if (directRes.ok) return normalized;
    } catch (_error) {
        // Fallback search below.
    }

    try {
        const fallbackRes = await fetch(`/api/lorries?page=1&page_size=1&query=${encodeURIComponent(searchValue)}&district=${encodeURIComponent(district)}`);
        if (!fallbackRes.ok) return '';
        const payload = await fallbackRes.json();
        return payload?.items?.[0]?.vehicle_id || '';
    } catch (_error) {
        return '';
    }
}

async function renderSingleLorryPanel(vehicleId) {
    const panel = document.getElementById('singleLorryPanel');
    if (!panel) return;

    if (!vehicleId) {
        panel.textContent = 'Search a lorry to view detailed live stats.';
        return;
    }

    try {
        const response = await fetch(`/api/vehicle/${encodeURIComponent(vehicleId)}/detail`);
        if (!response.ok) {
            panel.textContent = 'No lorry found for this search.';
            return;
        }
        const data = await response.json();
        const vehicle = data.vehicle || {};
        const behavior = vehicle.driver_behavior || {};
        panel.innerHTML = `
            District: <strong>${vehicle.district || 'Unknown'}</strong><br>
            Vehicle: <strong>${vehicle.vehicle_id || vehicleId}</strong><br>
            Route: ${vehicle.route_name || vehicle.route_id || '-'}<br>
            Profile: ${vehicle.profile || 'normal'}<br>
            Trips: ${vehicle.trips || 0} / 24h: ${vehicle.trips_24h || 0}<br>
            Risk: ${Number(vehicle.risk || 0).toFixed(1)} (${vehicle.risk_level || 'SAFE'})<br>
            Prediction: ${formatPredictionLabel(vehicle.prediction_label || 'LOW')} (${Math.round(Number(vehicle.prediction_probability || 0) * 100)}%)<br>
            Weight: ${Number(vehicle.predicted_weight || 0).toFixed(1)} tons ${vehicle.weight_locked ? '(Locked)' : '(Real-time)'}<br>
            Driver: harsh braking ${behavior.harsh_braking || 0}, fluctuation ${Number(behavior.speed_fluctuation || 0).toFixed(2)}, risky ${behavior.risky ? 'YES' : 'NO'}<br>
            Overload: ${vehicle.overload_flag ? 'YES' : 'NO'}<br>
            <a class="btn-link" href="/vehicles/${encodeURIComponent(vehicle.vehicle_id || vehicleId)}">Open full detail page</a>
        `;
    } catch (_error) {
        panel.textContent = 'Unable to load selected lorry detail.';
    }
}

async function refresh() {
    if (dashboardRefreshInFlight) {
        dashboardRefreshQueued = true;
        return;
    }

    dashboardRefreshInFlight = true;
    try {
        const district = dashboardState.district || '';
        const query = dashboardState.query || '';
        const [alertsRes, historyRes, overviewRes, tnStatsRes, mapContext] = await Promise.all([
            fetch(`/api/alerts?limit=60&district=${encodeURIComponent(district)}&query=${encodeURIComponent(query)}`),
            fetch(`/api/history/risk?minutes=240&district=${encodeURIComponent(district)}`),
            fetch('/api/ai-overview'),
            fetch(`/api/tn-dashboard-stats?district=${encodeURIComponent(district)}&query=${encodeURIComponent(query)}&page=${dashboardState.page}&page_size=${dashboardState.pageSize}`),
            refreshMapContext(),
        ]);

        const alerts = await alertsRes.json();
        const history = await historyRes.json();
        const overview = await overviewRes.json();
        const tnStats = await tnStatsRes.json();

        const mapContextData = mapContext || {};
        const lorryPage = mapContextData.lorries || { items: [], total: 0, page: 1, total_pages: 1 };
        const routes = mapContextData.routes || {};
        const heat = mapContextData.heatmap || [];

        const overall = tnStats.overall || {};
        const rowItems = lorryPage.items || [];
        const highRiskCount = rowItems.filter(item => Number(item.risk || 0) >= 80).length;
        const suspiciousCount = rowItems.filter(item => Number(item.risk || 0) >= 50 && Number(item.risk || 0) < 80).length;
        const tripsTotal = rowItems.reduce((sum, item) => sum + Number(item.trips || 0), 0);

        animateCountUp('vehicleCount', overall.active_trucks || rowItems.length || 0);
        animateCountUp('tripCount', tripsTotal);
        animateCountUp('dangerCount', highRiskCount);
        animateCountUp('suspiciousCount', suspiciousCount);
        setText('lastSync', `Last sync ${new Date().toLocaleTimeString()}`);

        renderAlerts(alerts);
        paintHeatmap(heat);
        renderVehicleCards(rowItems);
        
        map.invalidateSize();
        if (rowItems && rowItems.length > 0 && !window._mapBoundsSet) {
            const latLngs = rowItems
                .filter(item => item.lat && item.lon)
                .map(item => [item.lat, item.lon]);
            if (latLngs.length > 0) {
                try {
                    map.fitBounds(L.latLngBounds(latLngs).pad(0.12));
                    window._mapBoundsSet = true;
                } catch (err) {}
            }
        }

        renderRiskChart(history);
        if (selectedLorry) {
            renderSingleLorryPanel(selectedLorry);
        }

        const classification = overview.classification || {};
        const regression = overview.regression || {};
        const system = overview.system || {};

        animateCountUp('stackClassVehicles', classification.vehicles || 0);
        animateCountUp('stackClassHigh', classification.high_predictions || 0);
        animateCountUp('stackClassMedium', classification.medium_predictions || 0);
        animateCountUp('stackClassProb', `${Math.round(Number(classification.avg_probability || 0) * 100)}%`);
        animateCountUp('stackRegLocked', regression.locked_weight_predictions || 0);
        animateCountUp('stackRegOverload', regression.overloads || 0);
        animateCountUp('stackRegAvgWeight', `${Number(regression.avg_predicted_weight || 0).toFixed(1)} tons`);
        animateCountUp('stackSystemScale', `${system.configured_vehicles || 0} trucks / ${system.configured_routes || 0} routes`);

        animateCountUp('tnConfiguredTrucks', overall.configured_trucks || 0);
        animateCountUp('tnConfiguredRoutes', overall.configured_routes || 0);
        animateCountUp('tnConfiguredMines', overall.configured_mines || 0);
        animateCountUp('tnActiveTrucks', overall.active_trucks || 0);
        animateCountUp('tnOverloads', overall.overloads || 0);
        animateCountUp('tnAvgRisk', Number(overall.avg_risk || 0).toFixed(1));
        animateCountUp('tnAvgThreat', Number(overall.avg_final_threat || 0).toFixed(1));

        const districtBody = document.getElementById('districtStatsBody');
        if (districtBody) {
            const districts = (tnStats.districts || []).slice(0, 25);
            districtBody.innerHTML = districts.length
                ? districts.map(d => `
                    <tr class="district-row" data-district="${d.district}">
                        <td>${d.district}</td>
                        <td>${d.trucks}</td>
                        <td>${d.overloads}</td>
                        <td>${Number(d.avg_risk || 0).toFixed(1)}</td>
                        <td>${Number(d.avg_threat || 0).toFixed(1)}</td>
                    </tr>
                `).join('')
                : '<tr><td colspan="5">No district data yet.</td></tr>';
            districtBody.querySelectorAll('.district-row').forEach(row => {
                row.addEventListener('click', () => {
                    dashboardState.district = row.getAttribute('data-district') || '';
                    dashboardState.page = 1;
                    const districtSelect = document.getElementById('districtFilterSelect');
                    if (districtSelect) districtSelect.value = dashboardState.district;
                    refresh();
                    setMapCenterFromDistrict(dashboardState.district);
                });
            });
        }

        renderDistrictPills(tnStats.districts || []);

        const districtSelect = document.getElementById('districtFilterSelect');
        if (districtSelect && !districtSelect.dataset.bound) {
            districtSelect.addEventListener('change', () => {
                dashboardState.district = districtSelect.value || '';
                dashboardState.page = 1;
                refresh();
                setMapCenterFromDistrict(dashboardState.district);
            });
            districtSelect.dataset.bound = '1';
        }

        const singleLorryInput = document.getElementById('singleLorrySearchInput');
        const singleLorryBtn = document.getElementById('singleLorrySearchBtn');
        const singleLorryClear = document.getElementById('singleLorryClearBtn');
        if (singleLorryInput && !singleLorryInput.dataset.bound) {
            singleLorryInput.addEventListener('keydown', async event => {
                if (event.key !== 'Enter') return;
                const resolved = await resolveVehicleId(singleLorryInput.value, dashboardState.district || '');
                selectedLorry = resolved;
                if (!selectedLorry) {
                    renderSingleLorryPanel('');
                    return;
                }
                singleLorryInput.value = selectedLorry;
                renderSingleLorryPanel(selectedLorry);
            });
            singleLorryInput.dataset.bound = '1';
        }
        if (singleLorryBtn && !singleLorryBtn.dataset.bound) {
            singleLorryBtn.addEventListener('click', async () => {
                const resolved = await resolveVehicleId(singleLorryInput ? singleLorryInput.value : '', dashboardState.district || '');
                selectedLorry = resolved;
                if (!selectedLorry) {
                    renderSingleLorryPanel('');
                    return;
                }
                if (singleLorryInput) singleLorryInput.value = selectedLorry;
                renderSingleLorryPanel(selectedLorry);
            });
            singleLorryBtn.dataset.bound = '1';
        }
        if (singleLorryClear && !singleLorryClear.dataset.bound) {
            singleLorryClear.addEventListener('click', () => {
                selectedLorry = null;
                if (singleLorryInput) singleLorryInput.value = '';
                renderSingleLorryPanel('');
            });
            singleLorryClear.dataset.bound = '1';
        }

        const searchInput = document.getElementById('lorrySearchInput');
        const searchApplyBtn = document.getElementById('searchApplyBtn');
        const searchClearBtn = document.getElementById('searchClearBtn');
        if (searchInput && !searchInput.dataset.bound) {
            searchInput.addEventListener('keydown', event => {
                if (event.key === 'Enter') {
                    dashboardState.query = searchInput.value.trim();
                    dashboardState.page = 1;
                    refresh();
                }
            });
            searchInput.dataset.bound = '1';
        }
        if (searchApplyBtn && !searchApplyBtn.dataset.bound) {
            searchApplyBtn.addEventListener('click', () => {
                dashboardState.page = 1;
                dashboardState.query = searchInput ? searchInput.value.trim() : dashboardState.query;
                refresh();
            });
            searchApplyBtn.dataset.bound = '1';
        }
        if (searchClearBtn && !searchClearBtn.dataset.bound) {
            searchClearBtn.addEventListener('click', () => {
                dashboardState.query = '';
                dashboardState.district = '';
                dashboardState.page = 1;
                selectedLorry = '';
                if (searchInput) searchInput.value = '';
                if (districtSelect) districtSelect.value = '';
                refresh();
                setMapCenterFromDistrict('');
            });
            searchClearBtn.dataset.bound = '1';
        }

        renderPageControls(lorryPage, page => {
            dashboardState.page = page;
            refresh();
        });

        const routeIds = Object.keys(routes).sort();
        const routeSignature = `${dashboardState.district}|${routeIds.join('|')}`;
        if (routeSignature !== lastRouteSignature) {
            lastRouteSignature = routeSignature;
            routeLayers.forEach(layer => map.removeLayer(layer));
            routeLayers = [];
            const bounds = [];
            Object.values(routes).forEach(route => {
                const line = L.polyline(route.path, { color: route.color, weight: 4, dashArray: '8 7', opacity: 0.85 }).addTo(map);
                routeLayers.push(line);
                const mine = L.polygon(route.mine_zone.polygon, { color: route.color, fillColor: route.color, fillOpacity: 0.12, weight: 1.5 }).addTo(map);
                routeLayers.push(mine);
                const dump = L.polygon(route.dump_zone.polygon, { color: route.color, fillColor: route.color, fillOpacity: 0.12, weight: 1.5 }).addTo(map);
                routeLayers.push(dump);
                route.path.forEach(pt => bounds.push(pt));
            });
            if (bounds.length && dashboardState.district) {
                map.fitBounds(bounds, { padding: [18, 18] });
            }
        }

        renderDistrictPills(tnStats.districts || []);
    } catch (_error) {
        setText('lastSync', 'Unable to sync dashboard right now');
    } finally {
        dashboardRefreshInFlight = false;
        if (dashboardRefreshQueued) {
            dashboardRefreshQueued = false;
            refresh();
        }
    }
}

refresh();
setInterval(refresh, 5000);

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
