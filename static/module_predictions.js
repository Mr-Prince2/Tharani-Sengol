let mpCharts = {
    anomaly: null,
    forecast: null,
    driver: null,
    cluster: null,
    fusion: null,
    shap: null,
};

let latestModuleData = null;

function upsertChart(key, canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (mpCharts[key]) mpCharts[key].destroy();
    mpCharts[key] = new Chart(canvas.getContext('2d'), config);
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function buildExplainList(data) {
    const summary = data?.summary || {};
    const twin = data?.digital_twin || {};
    const anomalyDist = data?.anomaly?.distribution || {};
    const behavior = data?.driver_behavior || {};
    const clusters = data?.clusters || [];
    const shapTop = data?.shap?.top_features || [];

    const vehicles = Number(summary.vehicles || 0);
    const anomalyFlagged = Number(summary.anomaly_flagged || 0);
    const riskyDrivers = Number(summary.risky_drivers || 0);
    const highThreat = Number(summary.high_threat || 0);
    const overloads = Number(twin.overloads || 0);

    const anomalyPct = vehicles ? ((anomalyFlagged / vehicles) * 100).toFixed(1) : '0.0';
    const riskyPct = vehicles ? ((riskyDrivers / vehicles) * 100).toFixed(1) : '0.0';
    const highThreatPct = vehicles ? ((highThreat / vehicles) * 100).toFixed(1) : '0.0';

    const mostAnomalyBucket = Object.entries(anomalyDist).sort((a, b) => Number(b[1]) - Number(a[1]))[0];
    const safeAligned = Number(behavior?.safe?.aligned || 0);
    const safeCount = Number(behavior?.safe?.count || 0);
    const normalAligned = Number(behavior?.normal?.aligned || 0);
    const normalCount = Number(behavior?.normal?.count || 0);
    const highAligned = Number(behavior?.high_risk?.aligned || 0);
    const highCount = Number(behavior?.high_risk?.count || 0);
    const bestFeature = shapTop[0]?.feature || 'no dominant feature yet';

    const lines = [
        `Isolation model: ${anomalyFlagged} of ${vehicles} trucks (${anomalyPct}%) are currently anomaly-flagged. Most trucks are in score band ${mostAnomalyBucket ? mostAnomalyBucket[0] : 'n/a'}.`,
        `LSTM forecast: doughnut chart shows where trucks are predicted to move next (mine, dump, unknown). A heavier dump share usually means more loaded-return traffic.`,
        `Driver behavior: risky-driver rate is ${riskyPct}%. Profile alignment right now: safe ${safeAligned}/${safeCount}, normal ${normalAligned}/${normalCount}, high_risk ${highAligned}/${highCount}.`,
        `K-Means hotspots: ${clusters.length} hotspot clusters identified. Higher intensity clusters suggest repeated violations in those coordinates.`,
        `Fusion model: ${highThreat} trucks (${highThreatPct}%) are high-threat after combining risk, anomaly, weight, and behavior signals.`,
        `Digital twin: active trucks ${Number(twin.active_trucks || 0)}, routes ${Number(twin.configured_routes || 0)}, overloads ${overloads}, avg final threat ${Number(twin.avg_final_threat || 0).toFixed(2)}.`,
        `SHAP explainability: current strongest feature impact is ${bestFeature}. This helps explain why model outputs are high or low.`,
    ];

    return {
        summary: `Current system state indicates ${highThreatPct}% high-threat trucks and ${anomalyPct}% anomaly-flagged trucks. Use this panel to quickly interpret each module output in plain language.`,
        lines,
    };
}

function renderExplainPanel(data) {
    const summaryEl = document.getElementById('mpExplainSummary');
    const listEl = document.getElementById('mpExplainList');
    if (!summaryEl || !listEl) return;

    const explain = buildExplainList(data || {});
    summaryEl.textContent = explain.summary;
    listEl.innerHTML = explain.lines.map(item => `<li>${item}</li>`).join('');
}

async function refreshModulePredictions() {
    try {
        const response = await fetch('/api/module-predictions');
        const data = await response.json();
        latestModuleData = data;

        const summary = data.summary || {};
        setText('mpVehicles', summary.vehicles || 0);
        setText('mpAnomaly', summary.anomaly_flagged || 0);
        setText('mpRiskyDrivers', summary.risky_drivers || 0);
        setText('mpHighThreat', summary.high_threat || 0);

        const anomaly = data.anomaly || {};
        const anomalyDist = anomaly.distribution || {};
        upsertChart('anomaly', 'mpAnomalyChart', {
            type: 'bar',
            data: {
                labels: Object.keys(anomalyDist),
                datasets: [{
                    label: 'Vehicles',
                    data: Object.values(anomalyDist),
                    backgroundColor: 'rgba(59,130,246,0.5)',
                    borderColor: '#3b82f6',
                    borderWidth: 1,
                }],
            },
            options: { responsive: true },
        });

        const forecast = data.forecast || {};
        const zoneCounts = forecast.zone_counts || {};
        upsertChart('forecast', 'mpForecastChart', {
            type: 'doughnut',
            data: {
                labels: Object.keys(zoneCounts),
                datasets: [{
                    data: Object.values(zoneCounts),
                    backgroundColor: ['#10b981', '#f59e0b', '#64748b'],
                }],
            },
            options: { responsive: true },
        });

        const behavior = data.driver_behavior || {};
        const behaviorProfiles = Object.keys(behavior);
        upsertChart('driver', 'mpDriverChart', {
            type: 'bar',
            data: {
                labels: behaviorProfiles,
                datasets: [
                    {
                        label: 'Risky',
                        data: behaviorProfiles.map(key => Number(behavior[key]?.risky || 0)),
                        backgroundColor: 'rgba(239,68,68,0.55)',
                    },
                    {
                        label: 'Aligned',
                        data: behaviorProfiles.map(key => Number(behavior[key]?.aligned || 0)),
                        backgroundColor: 'rgba(16,185,129,0.55)',
                    },
                ],
            },
            options: { responsive: true },
        });

        const clusters = data.clusters || [];
        const topClusters = clusters.slice(0, 12);
        upsertChart('cluster', 'mpClusterChart', {
            type: 'line',
            data: {
                labels: topClusters.map(item => `C${item.cluster_id}`),
                datasets: [{
                    label: 'Intensity',
                    data: topClusters.map(item => Number(item.intensity || 0)),
                    borderColor: '#f97316',
                    backgroundColor: 'rgba(249,115,22,0.25)',
                    fill: true,
                    tension: 0.25,
                }],
            },
            options: { responsive: true },
        });

        const fusion = data.fusion || {};
        const topFusion = (fusion.top || []).slice(0, 12);
        upsertChart('fusion', 'mpFusionChart', {
            type: 'bar',
            data: {
                labels: topFusion.map(item => item.vehicle_id),
                datasets: [{
                    label: 'Final Threat Score',
                    data: topFusion.map(item => Number(item.final_threat_score || 0)),
                    backgroundColor: 'rgba(236,72,153,0.45)',
                    borderColor: '#ec4899',
                    borderWidth: 1,
                }],
            },
            options: { responsive: true, scales: { y: { min: 0, max: 100 } } },
        });

        const shap = data.shap || {};
        const topFeatures = shap.top_features || [];
        upsertChart('shap', 'mpShapChart', {
            type: 'bar',
            data: {
                labels: topFeatures.map(item => item.feature),
                datasets: [{
                    label: 'Impact',
                    data: topFeatures.map(item => Number(item.impact || 0)),
                    backgroundColor: 'rgba(14,165,233,0.45)',
                    borderColor: '#0ea5e9',
                    borderWidth: 1,
                }],
            },
            options: { responsive: true },
        });

        const twin = data.digital_twin || {};
        setText('mpTwinActive', twin.active_trucks || 0);
        setText('mpTwinRoutes', twin.configured_routes || 0);
        setText('mpTwinOverloads', twin.overloads || 0);
        setText('mpTwinThreat', Number(twin.avg_final_threat || 0).toFixed(2));

        renderExplainPanel(data);
    } catch (_error) {
        // Keep last successful charts visible.
    }
}

const mpExplainBtn = document.getElementById('mpExplainBtn');
const mpExplainPanel = document.getElementById('mpExplainPanel');
if (mpExplainBtn && mpExplainPanel) {
    mpExplainBtn.addEventListener('click', () => {
        if (latestModuleData) renderExplainPanel(latestModuleData);
        const isHidden = mpExplainPanel.classList.contains('hidden');
        mpExplainPanel.classList.toggle('hidden', !isHidden);
        mpExplainBtn.textContent = isHidden ? 'Hide Explanation' : 'Explain Current Predictions';
    });
}

refreshModulePredictions();
setInterval(refreshModulePredictions, 6000);
