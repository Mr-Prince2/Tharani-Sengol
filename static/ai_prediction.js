function formatNumber(value, digits = 1) {
    const number = Number(value || 0);
    return number.toFixed(digits);
}

function riskClass(risk) {
    if (risk >= 80) return 'danger';
    if (risk >= 50) return 'suspicious';
    return 'safe';
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

let weightTrendChart = null;
let aiRefreshInFlight = false;
let aiRefreshQueued = false;
let aiState = {
    query: '',
    district: '',
    page: 1,
    pageSize: 4,
};

function minuteBucket(isoTime) {
    const date = new Date(isoTime);
    if (Number.isNaN(date.getTime())) return null;
    date.setSeconds(0, 0);
    return date.toISOString();
}

function renderWeightTrendChart(rows) {
    const canvas = document.getElementById('weightHistoryChart');
    if (!canvas) return;

    const buckets = new Map();
    rows.forEach(item => {
        const history = item.weight_history || [];
        history.slice(-30).forEach(point => {
            const bucket = minuteBucket(point.ts);
            if (!bucket) return;
            if (!buckets.has(bucket)) {
                buckets.set(bucket, { ts: bucket, weightSum: 0, weightCount: 0, overloadCount: 0 });
            }
            const entry = buckets.get(bucket);
            entry.weightSum += Number(point.weight || 0);
            entry.weightCount += 1;
            if (point.overload) entry.overloadCount += 1;
        });
    });

    const sorted = Array.from(buckets.values()).sort((left, right) => left.ts.localeCompare(right.ts)).slice(-24);
    const labels = sorted.map(item => new Date(item.ts).toLocaleTimeString());
    const avgWeights = sorted.map(item => item.weightCount ? Number((item.weightSum / item.weightCount).toFixed(2)) : 0);
    const overloadCounts = sorted.map(item => item.overloadCount);

    if (weightTrendChart) weightTrendChart.destroy();

    weightTrendChart = new Chart(canvas.getContext('2d'), {
        data: {
            labels,
            datasets: [
                {
                    type: 'line',
                    label: 'Avg Predicted Weight (tons)',
                    data: avgWeights,
                    borderColor: '#38bdf8',
                    backgroundColor: '#38bdf8',
                    yAxisID: 'y',
                    tension: 0.25,
                    pointRadius: 0,
                },
                {
                    type: 'bar',
                    label: 'Overload Events',
                    data: overloadCounts,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.45)',
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Tons' } },
                y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Events' } },
            },
        },
    });
}

function renderPagination(rootId, meta, onPageChange) {
    const root = document.getElementById(rootId);
    if (!root) return;
    const totalPages = Number(meta.total_pages || 1);
    const page = Number(meta.page || 1);
    const chips = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);
    for (let index = start; index <= end; index += 1) {
        chips.push(`<button class="page-chip ${index === page ? 'active' : ''}" data-page="${index}" type="button">${index}</button>`);
    }

    root.innerHTML = `
        <button class="page-chip" data-nav="prev" type="button" ${page <= 1 ? 'disabled' : ''}>Prev</button>
        ${chips.join('')}
        <button class="page-chip" data-nav="next" type="button" ${page >= totalPages ? 'disabled' : ''}>Next</button>
        <span class="muted">Page ${page} of ${totalPages} | ${meta.total || 0} trucks</span>
    `;

    root.querySelectorAll('[data-page]').forEach(btn => btn.addEventListener('click', () => onPageChange(Number(btn.getAttribute('data-page')))));
    root.querySelectorAll('[data-nav]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.getAttribute('data-nav') === 'prev') onPageChange(Math.max(1, page - 1));
            if (btn.getAttribute('data-nav') === 'next') onPageChange(Math.min(totalPages, page + 1));
        });
    });
}

function renderDistrictSelect(districts) {
    const select = document.getElementById('aiDistrictSelect');
    if (!select) return;
    const current = select.value;
    const options = [{ district: '', label: 'All Districts' }, ...(districts || []).map(item => ({ district: item.district, label: item.district }))];
    select.innerHTML = options.map(item => `<option value="${item.district}">${item.label}</option>`).join('');
    if (aiState.district) {
        select.value = aiState.district;
    } else if (current) {
        select.value = current;
    }
}

function renderModuleCards(overview) {
    const root = document.getElementById('aiConfiguredTrucks');
    if (root) root.textContent = overview?.system?.configured_vehicles || 0;
}

async function refreshAIPredictionPage() {
    if (aiRefreshInFlight) {
        aiRefreshQueued = true;
        return;
    }

    aiRefreshInFlight = true;
    try {
        const district = aiState.district || '';
        const query = aiState.query || '';
        const [lorriesRes, alertsRes, overviewRes, tnStatsRes] = await Promise.all([
            fetch(`/api/lorries?page=${aiState.page}&page_size=${aiState.pageSize}&query=${encodeURIComponent(query)}&district=${encodeURIComponent(district)}`),
            fetch(`/api/alerts?limit=150&district=${encodeURIComponent(district)}&query=${encodeURIComponent(query)}`),
            fetch('/api/ai-overview'),
            fetch('/api/tn-dashboard-stats?page=1&page_size=1'),
        ]);

        const lorries = await lorriesRes.json();
        const alerts = await alertsRes.json();
        const overview = await overviewRes.json();
        const tnStats = await tnStatsRes.json();

    const latestPredictionAlerts = {};
    alerts.forEach(alert => {
        if (!alert || !alert.vehicle_id || !alert.message) return;
        const text = String(alert.message).toLowerCase();
        if (!text.includes('predicted high violation probability')) return;
        if (!latestPredictionAlerts[alert.vehicle_id]) latestPredictionAlerts[alert.vehicle_id] = alert;
    });

        const rows = lorries.items || [];
        let overloadCount = 0;
        let weightSum = 0;
        let weightCount = 0;
        let highRiskCount = 0;

        const cardsRoot = document.getElementById('aiPredictionCards');
        const tableRoot = document.getElementById('aiPredictionTableBody');

        if (cardsRoot) {
            cardsRoot.innerHTML = rows.map(row => {
            const prediction = row.prediction_label ? { label: row.prediction_label, probability: row.prediction_probability || 0, reason: row.last_event || 'n/a' } : { label: 'LOW', probability: 0, reason: 'n/a' };
            const predictionLabel = formatPredictionLabel(prediction.label);
            const risk = Number(row.risk || 0);
            const lockedWeight = Boolean(row.weight_locked);
            const overload = Boolean(row.overload_flag);
            const alertReason = latestPredictionAlerts[row.vehicle_id]?.message || '';
            const weight = Number(row.predicted_weight || 0);
            if (overload) overloadCount += 1;
            if (risk >= 80) highRiskCount += 1;
            if (weight > 0) {
                weightSum += weight;
                weightCount += 1;
            }

            const explainParts = [prediction.reason || 'stable trend'];
            if (alertReason) explainParts.push(alertReason);
            if (!lockedWeight) explainParts.push(`weight lock pending until ${Number(overview?.regression?.lock_distance_km || 0.35).toFixed(2)} km`);

            return `
                <article class="vehicle-card ${overload ? 'overload-card' : ''}">
                    <h3>${row.vehicle_id}</h3>
                    <div class="vehicle-meta">
                        District: <strong>${row.district || 'Unknown'}</strong><br>
                        Trips: ${row.trips || 0} total / ${row.trips_24h || 0} in 24h<br>
                        Risk: ${risk.toFixed(1)}<br>
                        Prediction: ${predictionLabel} (${Math.round((prediction.probability || 0) * 100)}%)<br>
                        Weight: ${formatNumber(weight)} tons ${lockedWeight ? '(Locked)' : '(Real-time)'}<br>
                        Avg Weight: ${formatNumber(row.average_weight || 0)} tons<br>
                        Overload: ${overload ? 'YES' : 'NO'}<br>
                        Why: ${explainParts.join(' | ')}
                    </div>
                    <span class="badge ${riskClass(risk)}">${overload ? 'OVERLOAD' : 'NORMAL'}</span>
                </article>
            `;
            }).join('');
        }

        if (tableRoot) {
            tableRoot.innerHTML = rows.map(row => {
            const prediction = row.prediction_label ? { label: row.prediction_label, probability: row.prediction_probability || 0, reason: row.last_event || 'n/a' } : { label: 'LOW', probability: 0, reason: 'n/a' };
            const predictionLabel = formatPredictionLabel(prediction.label);
            const risk = Number(row.risk || 0);
            const lockedWeight = Boolean(row.weight_locked);
            const overload = Boolean(row.overload_flag);
            const alertReason = latestPredictionAlerts[row.vehicle_id]?.message || '';
            const why = [prediction.reason || 'stable trend'];
            if (alertReason) why.push(alertReason);
            if (!lockedWeight) why.push(`weight lock pending until ${Number(overview?.regression?.lock_distance_km || 0.35).toFixed(2)} km`);

            return `
                <tr>
                    <td>${row.vehicle_id}</td>
                    <td>${row.trips || 0}</td>
                    <td>${risk.toFixed(1)}</td>
                    <td>${predictionLabel} (${Math.round((prediction.probability || 0) * 100)}%)</td>
                    <td>${formatNumber(row.predicted_weight || 0)} tons ${lockedWeight ? '(Locked)' : '(Real-time)'}</td>
                    <td>${formatNumber(row.average_weight || 0)} tons</td>
                    <td>${overload ? 'YES' : 'NO'}</td>
                    <td>${why.join(' | ')}</td>
                </tr>
            `;
            }).join('') || '<tr><td colspan="8">No live prediction data available.</td></tr>';
        }

        document.getElementById('aiVehicleCount').textContent = lorries.total || 0;
        document.getElementById('aiHighRiskCount').textContent = highRiskCount;
        document.getElementById('aiOverloadCount').textContent = overloadCount;
        document.getElementById('aiAverageWeight').textContent = weightCount ? `${(weightSum / weightCount).toFixed(1)} tons` : '0.0 tons';

        const system = overview.system || {};
        const regression = overview.regression || {};
        const modules = overview.modules || {};
        const twin = overview.digital_twin || {};
        document.getElementById('aiConfiguredTrucks').textContent = system.configured_vehicles || 0;
        document.getElementById('aiConfiguredRoutes').textContent = system.configured_routes || 0;
        document.getElementById('aiMineZones').textContent = system.configured_mine_zones || 0;
        document.getElementById('aiDumpZones').textContent = system.configured_dump_zones || 0;

        const moduleRows = {
            moduleIsolation: modules.anomaly_enabled ? 'ON' : 'OFF',
            moduleLstm: modules.time_series_enabled ? 'ON' : 'OFF',
            moduleDriver: modules.driver_behavior_enabled ? 'ON' : 'OFF',
            moduleKmeans: modules.clustering_enabled ? 'ON' : 'OFF',
            moduleFusion: modules.fusion_enabled ? 'ON' : 'OFF',
            moduleShap: modules.explainability_enabled ? 'ON' : 'OFF',
            moduleTwin: twin.active_trucks !== undefined ? 'ON' : 'OFF',
        };
        Object.entries(moduleRows).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });

        const lockDistance = Number(regression.lock_distance_km || 0.35);
        const lockHours = Number(regression.lock_trip_minutes || 0) / 60;
        const moduleInfo = document.getElementById('aiModuleRuntimeInfo');
        if (moduleInfo) {
            moduleInfo.textContent = `Weight lock triggers after about ${lockDistance.toFixed(2)} km (${lockHours.toFixed(2)} hours minimum trip age).`;
        }

        renderDistrictSelect((tnStats.districts || []).slice(0, 25));
        renderPagination('aiPageControls', lorries, page => {
            aiState.page = page;
            refreshAIPredictionPage();
        });
        renderWeightTrendChart(rows);
    } catch (_error) {
        const tableRoot = document.getElementById('aiPredictionTableBody');
        if (tableRoot) tableRoot.innerHTML = '<tr><td colspan="8">Unable to load AI predictions right now.</td></tr>';
    } finally {
        aiRefreshInFlight = false;
        if (aiRefreshQueued) {
            aiRefreshQueued = false;
            refreshAIPredictionPage();
        }
    }
}

const aiSearchInput = document.getElementById('aiSearchInput');
const aiDistrictSelect = document.getElementById('aiDistrictSelect');
const aiSearchApplyBtn = document.getElementById('aiSearchApplyBtn');
const aiSearchClearBtn = document.getElementById('aiSearchClearBtn');

if (aiSearchApplyBtn) {
    aiSearchApplyBtn.addEventListener('click', () => {
        aiState.query = aiSearchInput ? aiSearchInput.value.trim() : '';
        aiState.district = aiDistrictSelect ? aiDistrictSelect.value || '' : '';
        aiState.page = 1;
        refreshAIPredictionPage();
    });
}

if (aiSearchClearBtn) {
    aiSearchClearBtn.addEventListener('click', () => {
        aiState.query = '';
        aiState.district = '';
        aiState.page = 1;
        if (aiSearchInput) aiSearchInput.value = '';
        if (aiDistrictSelect) aiDistrictSelect.value = '';
        refreshAIPredictionPage();
    });
}

if (aiDistrictSelect) {
    aiDistrictSelect.addEventListener('change', () => {
        aiState.district = aiDistrictSelect.value || '';
        aiState.page = 1;
        refreshAIPredictionPage();
    });
}

refreshAIPredictionPage();
setInterval(refreshAIPredictionPage, 5000);
