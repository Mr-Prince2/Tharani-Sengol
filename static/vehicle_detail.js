function safeNumber(value, digits = 1) {
    return Number(value || 0).toFixed(digits);
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

function renderList(rootId, items, mapFn, emptyMessage) {
    const root = document.getElementById(rootId);
    if (!root) return;
    if (!items || !items.length) {
        root.innerHTML = `<div class="muted">${emptyMessage}</div>`;
        return;
    }
    root.innerHTML = items.map(mapFn).join('');
}

async function refreshVehicleDetail() {
    const vehicleId = window.VEHICLE_DETAIL_ID;
    if (!vehicleId) return;

    try {
        const response = await fetch(`/api/vehicle/${encodeURIComponent(vehicleId)}/detail`);
        if (!response.ok) {
            const summary = document.getElementById('vehicleDetailSummary');
            if (summary) summary.textContent = 'Vehicle not found.';
            return;
        }

        const data = await response.json();
        const vehicle = data.vehicle || {};
        const explain = data.explain || {};
        const behavior = vehicle.driver_behavior || {};

        const summary = document.getElementById('vehicleDetailSummary');
        if (summary) {
            summary.innerHTML = `
                District: <strong>${vehicle.district || 'Unknown'}</strong><br>
                Profile: <strong>${vehicle.profile || 'normal'}</strong><br>
                Route: ${vehicle.route_name || vehicle.route_id || '-'}<br>
                Zone: ${vehicle.zone_name || 'Outside'}<br>
                Trips: ${vehicle.trips || 0} total / ${vehicle.trips_24h || 0} in 24h<br>
                Risk: ${safeNumber(vehicle.risk || 0)} (${vehicle.risk_level || 'SAFE'})<br>
                Prediction: ${formatPredictionLabel(vehicle.prediction_label || 'LOW')} (${Math.round(Number(vehicle.prediction_probability || 0) * 100)}%)<br>
                Weight: ${vehicle.weight_locked ? `${safeNumber(vehicle.predicted_weight || 0)} tons` : 'Pending'}<br>
                Avg Weight: ${safeNumber(vehicle.average_weight || 0)} tons<br>
                Overload: ${vehicle.overload_flag ? 'YES' : 'NO'}<br>
                Driver Behavior: harsh braking ${behavior.harsh_braking || 0}, speed fluctuation ${safeNumber(behavior.speed_fluctuation || 0, 2)}, risky ${behavior.risky ? 'YES' : 'NO'}<br>
                Anomaly Score: ${safeNumber(vehicle.anomaly_score || 0, 3)}<br>
                Final Threat: ${safeNumber(vehicle.final_threat_score || 0)}<br>
                Updated: ${vehicle.updated_at || 'n/a'}
            `;
        }

        const explainRoot = document.getElementById('vehicleDetailExplain');
        if (explainRoot) {
            const reasons = (explain.risk_reasons || []).slice(0, 5).map(item => `${item.reason} (+${item.points})`).join('; ');
            const safe = (explain.safe_reasons || []).slice(0, 4).join('; ');
            explainRoot.innerHTML = `
                Risk Level: <strong>${explain.risk_level || 'SAFE'}</strong><br>
                Risk Score: ${safeNumber(explain.risk || 0)}<br>
                Why risky: ${reasons || 'No recent high-risk triggers'}<br>
                Safe signals: ${safe || 'No strong safe signals'}
            `;
        }

        renderList(
            'vehicleDetailAlerts',
            data.alerts || [],
            item => `<div class="alert-item ${item.severity === 'critical' ? 'critical' : ''}"><strong>${item.severity || 'warning'}</strong> ${item.message}<br>${item.alert_time || 'n/a'}</div>`,
            'No recent alerts'
        );

        renderList(
            'vehicleDetailViolations',
            data.violations || [],
            item => `<div class="alert-item ${item.severity === 'critical' ? 'critical' : ''}"><strong>${item.reason}</strong> (+${item.points || 0})<br>Risk after: ${safeNumber(item.risk_after || 0)} | ${item.event_time || 'n/a'}</div>`,
            'No recent violations'
        );

        const pathBody = document.getElementById('vehicleDetailPathBody');
        if (pathBody) {
            const points = data.path || [];
            pathBody.innerHTML = points.length
                ? points.map(point => `
                    <tr>
                        <td>${point.event_time || 'n/a'}</td>
                        <td>${safeNumber(point.lat || 0, 5)}</td>
                        <td>${safeNumber(point.lon || 0, 5)}</td>
                        <td>${point.zone_name || point.zone_type || 'Outside'}</td>
                        <td>${safeNumber(point.risk || 0)}</td>
                        <td>${formatPredictionLabel(point.prediction_label || 'LOW')}</td>
                        <td>${safeNumber(point.predicted_weight || 0)} tons</td>
                    </tr>
                `).join('')
                : '<tr><td colspan="7">No recent path points available.</td></tr>';
        }
    } catch (error) {
        const summary = document.getElementById('vehicleDetailSummary');
        if (summary) summary.textContent = 'Unable to load vehicle detail right now.';
    }
}

refreshVehicleDetail();
setInterval(refreshVehicleDetail, 7000);
