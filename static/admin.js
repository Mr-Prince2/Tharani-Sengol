const ADMIN_PAGE_SIZE = 25;
let adminPage = 1;

function renderAdminPagination() {
    const root = document.getElementById('adminPageControls');
    const tableBody = document.querySelector('#adminTable tbody');
    if (!root || !tableBody) return;

    const rows = Array.from(tableBody.querySelectorAll('tr'));
    const total = rows.length;
    const totalPages = Math.max(1, Math.ceil(total / ADMIN_PAGE_SIZE));
    adminPage = Math.max(1, Math.min(adminPage, totalPages));

    const start = (adminPage - 1) * ADMIN_PAGE_SIZE;
    const end = start + ADMIN_PAGE_SIZE;
    rows.forEach((row, index) => {
        row.style.display = (index >= start && index < end) ? '' : 'none';
    });

    const chips = [];
    const from = Math.max(1, adminPage - 2);
    const to = Math.min(totalPages, adminPage + 2);
    for (let idx = from; idx <= to; idx += 1) {
        chips.push(`<button class="page-chip ${idx === adminPage ? 'active' : ''}" data-page="${idx}" type="button">${idx}</button>`);
    }

    root.innerHTML = `
        <button class="page-chip" data-nav="prev" type="button" ${adminPage <= 1 ? 'disabled' : ''}>Prev</button>
        ${chips.join('')}
        <button class="page-chip" data-nav="next" type="button" ${adminPage >= totalPages ? 'disabled' : ''}>Next</button>
        <span class="muted">Page ${adminPage} of ${totalPages} | ${total} vehicles</span>
    `;

    root.querySelectorAll('[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            adminPage = Number(btn.getAttribute('data-page'));
            renderAdminPagination();
        });
    });
    root.querySelectorAll('[data-nav]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.getAttribute('data-nav') === 'prev') adminPage = Math.max(1, adminPage - 1);
            if (btn.getAttribute('data-nav') === 'next') adminPage = adminPage + 1;
            renderAdminPagination();
        });
    });
}

async function saveRow(row) {
    const vehicleId = row.getAttribute('data-vehicle');
    const payload = {
        vehicle_id: vehicleId,
        profile: row.querySelector('.profile').value,
        allowed_24h_trips: Number(row.querySelector('.allowed').value || 0),
        rolling_window_hours: Number(row.querySelector('.window').value || 24),
        start_hour: Number(row.querySelector('.start').value || 0),
        end_hour: Number(row.querySelector('.end').value || 24),
    };

    const status = document.getElementById('adminStatus');
    status.textContent = `Saving ${vehicleId}...`;

    const response = await fetch('/api/admin/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        status.textContent = `Failed to save ${vehicleId}`;
        return;
    }
    status.textContent = `Saved ${vehicleId} at ${new Date().toLocaleTimeString()}`;
}

async function loadControlState() {
    const status = document.getElementById('controlStateText');
    try {
        const response = await fetch('/api/control-state');
        const state = await response.json();
        document.getElementById('weatherSel').value = state.weather || 'clear';
        document.getElementById('shiftSel').value = state.shift_mode || 'auto';
        document.getElementById('gpsNoise').value = Number(state.gps_noise || 0.1).toFixed(2);
        document.getElementById('cameraNoise').value = Number(state.camera_noise || 0.1).toFixed(2);
        document.getElementById('anomalyFactor').value = Number(state.anomaly_factor || 1.0).toFixed(2);
        document.getElementById('trafficFactor').value = Number(state.traffic_factor || 1.0).toFixed(2);
        status.textContent = `Scenario=${state.scenario}, weather=${state.weather}, active_shift=${state.active_shift}`;
    } catch {
        status.textContent = 'Unable to load control state';
    }
}

async function saveControlState() {
    const status = document.getElementById('controlStateText');
    status.textContent = 'Saving control settings...';
    const payload = {
        weather: document.getElementById('weatherSel').value,
        shift_mode: document.getElementById('shiftSel').value,
        gps_noise: Number(document.getElementById('gpsNoise').value || 0.1),
        camera_noise: Number(document.getElementById('cameraNoise').value || 0.1),
        anomaly_factor: Number(document.getElementById('anomalyFactor').value || 1.0),
        traffic_factor: Number(document.getElementById('trafficFactor').value || 1.0),
    };
    const response = await fetch('/api/admin/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        status.textContent = 'Failed to save control settings';
        return;
    }
    const result = await response.json();
    status.textContent = `Saved. Scenario=${result.control_state.scenario}, active_shift=${result.active_shift}`;
}

async function applyPreset(presetName) {
    const status = document.getElementById('controlStateText');
    status.textContent = `Applying preset ${presetName}...`;
    const response = await fetch('/api/admin/scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset: presetName }),
    });
    if (!response.ok) {
        status.textContent = `Failed to apply ${presetName}`;
        return;
    }
    await loadControlState();
}

document.querySelectorAll('.save-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const row = btn.closest('tr');
        saveRow(row);
    });
});

const resetBtn = document.getElementById('resetDataBtn');
if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
        const status = document.getElementById('adminStatus');
        status.textContent = 'Resetting runtime and event data...';
        const response = await fetch('/api/admin/reset-runtime', { method: 'POST' });
        if (!response.ok) {
            status.textContent = 'Reset failed';
            return;
        }
        status.textContent = 'Reset completed. Restart simulator to repopulate data.';
    });
}

document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        applyPreset(btn.getAttribute('data-preset'));
    });
});

const saveControlBtn = document.getElementById('saveControlBtn');
if (saveControlBtn) {
    saveControlBtn.addEventListener('click', saveControlState);
}

loadControlState();
renderAdminPagination();
