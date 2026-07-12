const map = L.map('map').setView([10.816, 78.730], 8);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; CARTO'
}).addTo(map);

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
    if (risk >= 80) return { color: '#ff0000', cls: 'danger', label: 'Risky Vehicle' };
    if (risk >= 50) return { color: '#eab308', cls: 'suspicious', label: 'Suspicious Activity' };
    return { color: '#22c55e', cls: 'safe', label: 'Authorized Vehicle' };
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
        root.innerHTML = '<div class="alert-item">No alerts yet.</div>';
        return;
    }
    root.innerHTML = alerts.slice(0, 12).map(item => {
        const cls = item.severity === 'critical' ? 'critical' : '';
        return `<div class="alert-item ${cls}"><strong>${item.vehicle_id}</strong> ${item.message}<br>${formatTs(item.time)}</div>`;
    }).join('');
}

async function showRiskExplain(vehicleId) {
    const response = await fetch(`/api/vehicle/${vehicleId}/explain`);
    const details = await response.json();

    document.getElementById('explainTitle').textContent = `${vehicleId} Risk Explanation`;
    document.getElementById('explainSummary').textContent = `Risk ${details.risk} (${details.risk_level}), prediction ${formatPredictionLabel(details.prediction.label)} (${Math.round((details.prediction.probability || 0) * 100)}%), weight ${Number(details.weight_prediction?.predicted_weight || 0).toFixed(1)} tons, overload ${details.weight_prediction?.overload_flag ? 'YES' : 'NO'}. ${details.prediction.reason}`;
    document.getElementById('heatHelp').textContent = details.how_heatmap_works;

    const riskList = document.getElementById('riskReasonsList');
    const safeList = document.getElementById('safeReasonsList');
    riskList.innerHTML = (details.risk_reasons || []).map(item => `<li>${item.reason} (+${item.points}) at ${formatTs(item.time)}</li>`).join('') || '<li>No recent risk triggers</li>';
    safeList.innerHTML = (details.safe_reasons || []).map(item => `<li>${item}</li>`).join('') || '<li>No safe signals identified</li>';
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

        if (position) {
            if (!markers[item.vehicle_id]) {
                markers[item.vehicle_id] = L.circleMarker(position, {
                    radius: 7,
                    color: style.color,
                    fillColor: style.color,
                    fillOpacity: 0.92,
                    weight: 2,
                }).addTo(map);
            } else {
                markers[item.vehicle_id].setLatLng(position);
                markers[item.vehicle_id].setStyle({ color: style.color, fillColor: style.color });
            }
            markers[item.vehicle_id].bindPopup(
                `<b>${item.vehicle_id}</b><br>District: ${item.district || 'Unknown'}<br>Profile: ${profile}<br>Risk: ${risk.toFixed(1)}<br>Prediction: ${predictionLabel} (${Math.round((prediction.probability || 0) * 100)}%)<br>Weight: ${weight.toFixed(1)} tons ${weightLocked ? '(Locked)' : '(Real-time)'}<br>Overload: ${overload ? 'YES' : 'NO'}<br>Zone: ${zone}`
            );
        }

        return `
            <article class="vehicle-card" style="border-left-color:${style.color}">
                <h3>${item.vehicle_id}</h3>
                <div class="vehicle-meta">
                    District: <strong>${item.district || 'Unknown'}</strong><br>
                    Profile: <strong>${profile}</strong><br>
                    Route: ${item.route_name || item.route_id || '-'}<br>
                    Zone: ${zone}<br>
                    Trips: ${item.trips || 0} total / ${item.trips_24h || 0} in 24h<br>
                    Risk: ${risk.toFixed(1)}<br>
                    Prediction: ${predictionLabel} (${Math.round((prediction.probability || 0) * 100)}%)<br>
                    Weight: ${weight.toFixed(1)} tons ${weightLocked ? '(Locked)' : '(Real-time)'}<br>
                    Avg Weight: ${averageWeight.toFixed(1)} tons<br>
                    Overload: ${overload ? 'YES' : 'NO'}<br>
                    Threat: ${Number(item.final_threat_score || 0).toFixed(1)}<br>
                    Last Event: ${item.last_event || 'n/a'}
                </div>
                <span class="badge ${style.cls}" data-vehicle-id="${item.vehicle_id}">${style.label} • ${risk.toFixed(1)}</span>
                <div style="margin-top:8px;"><a class="btn-link" href="/vehicles/${encodeURIComponent(item.vehicle_id)}">Open Full Details</a></div>
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

    historyChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            scales: { y: { min: 0, max: 100 } },
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

        setText('vehicleCount', overall.active_trucks || rowItems.length || 0);
        setText('tripCount', tripsTotal);
        setText('dangerCount', highRiskCount);
        setText('suspiciousCount', suspiciousCount);
        setText('lastSync', `Last sync ${new Date().toLocaleTimeString()}`);

        renderAlerts(alerts);
        paintHeatmap(heat);
        renderVehicleCards(rowItems);
        renderRiskChart(history);
        if (selectedLorry) {
            renderSingleLorryPanel(selectedLorry);
        }

        const classification = overview.classification || {};
        const regression = overview.regression || {};
        const system = overview.system || {};

        setText('stackClassVehicles', classification.vehicles || 0);
        setText('stackClassHigh', classification.high_predictions || 0);
        setText('stackClassMedium', classification.medium_predictions || 0);
        setText('stackClassProb', `${Math.round(Number(classification.avg_probability || 0) * 100)}%`);
        setText('stackRegLocked', regression.locked_weight_predictions || 0);
        setText('stackRegOverload', regression.overloads || 0);
        setText('stackRegAvgWeight', `${Number(regression.avg_predicted_weight || 0).toFixed(1)} tons`);
        setText('stackSystemScale', `${system.configured_vehicles || 0} trucks / ${system.configured_routes || 0} routes`);

        setText('tnConfiguredTrucks', overall.configured_trucks || 0);
        setText('tnConfiguredRoutes', overall.configured_routes || 0);
        setText('tnConfiguredMines', overall.configured_mines || 0);
        setText('tnActiveTrucks', overall.active_trucks || 0);
        setText('tnOverloads', overall.overloads || 0);
        setText('tnAvgRisk', Number(overall.avg_risk || 0).toFixed(1));
        setText('tnAvgThreat', Number(overall.avg_final_threat || 0).toFixed(1));

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
