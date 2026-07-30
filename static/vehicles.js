let vehiclesState = {
    query: '',
    district: '',
    page: 1,
    pageSize: 25,
};

let vehiclesRefreshInFlight = false;
let vehiclesRefreshQueued = false;

function formatValue(value, digits = 1) {
    const num = Number(value || 0);
    return num.toFixed(digits);
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

function renderVehiclesPagination(meta) {
    const root = document.getElementById('vehiclesPageControls');
    if (!root) return;

    const totalPages = Number(meta.total_pages || 1);
    const page = Number(meta.page || 1);
    const chips = [];
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);

    for (let index = start; index <= end; index += 1) {
        chips.push(`<button class="page-chip ${index === page ? 'active' : ''}" type="button" data-page="${index}">${index}</button>`);
    }

    root.innerHTML = `
        <button class="page-chip" type="button" data-nav="prev" ${page <= 1 ? 'disabled' : ''}>Prev</button>
        ${chips.join('')}
        <button class="page-chip" type="button" data-nav="next" ${page >= totalPages ? 'disabled' : ''}>Next</button>
        <span class="muted">Page ${page} of ${totalPages} | ${meta.total || 0} trucks</span>
    `;

    root.querySelectorAll('[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            vehiclesState.page = Number(btn.getAttribute('data-page'));
            refreshVehicles();
        });
    });

    root.querySelectorAll('[data-nav]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.getAttribute('data-nav') === 'prev') vehiclesState.page = Math.max(1, page - 1);
            if (btn.getAttribute('data-nav') === 'next') vehiclesState.page = Math.min(totalPages, page + 1);
            refreshVehicles();
        });
    });
}

function renderDistrictSelect(districts) {
    const select = document.getElementById('vehiclesDistrictSelect');
    if (!select) return;

    const options = [{ district: '', label: 'All Districts' }, ...(districts || []).map(item => ({ district: item.district, label: item.district }))];
    const previous = select.value;
    select.innerHTML = options.map(item => `<option value="${item.district}">${item.label}</option>`).join('');
    select.value = vehiclesState.district || previous || '';
}

function renderVehiclesTable(items) {
    const body = document.getElementById('vehiclesTableBody');
    if (!body) return;

    if (!items.length) {
        body.innerHTML = '<tr><td colspan="12"><div class="empty-state"><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg><div>No vehicles match the current filters.</div></div></td></tr>';
        return;
    }

    body.innerHTML = items.map(item => {
        const prediction = `${formatPredictionLabel(item.prediction_label || 'LOW')} (${Math.round(Number(item.prediction_probability || 0) * 100)}%)`;
        const detailHref = `/vehicles/${encodeURIComponent(item.vehicle_id)}`;
        return `
            <tr>
                <td><a class="link-inline" href="${detailHref}">${item.vehicle_id}</a></td>
                <td>${item.district || 'Unknown'}</td>
                <td>${item.profile || 'normal'}</td>
                <td>${item.route_name || item.route_id || '-'}</td>
                <td>${item.zone_name || 'Outside'}</td>
                <td>${item.trips || 0}</td>
                <td>${item.trips_24h || 0}</td>
                <td>${formatValue(item.risk || 0)} (${item.risk_level || 'SAFE'})</td>
                <td>${prediction}</td>
                <td>${item.weight_locked ? `${formatValue(item.predicted_weight || 0)} tons` : 'Pending'}<br><span class="muted">avg ${formatValue(item.average_weight || 0)} tons</span></td>
                <td>${item.overload_flag ? '<span class="status-yes">YES</span>' : '<span class="status-no">NO</span>'}</td>
                <td>${item.updated_at || 'n/a'}</td>
            </tr>
        `;
    }).join('');
}

async function refreshVehicles() {
    if (vehiclesRefreshInFlight) {
        vehiclesRefreshQueued = true;
        return;
    }

    vehiclesRefreshInFlight = true;
    try {
        const [lorriesRes, districtsRes] = await Promise.all([
            fetch(`/api/lorries?page=${vehiclesState.page}&page_size=${vehiclesState.pageSize}&query=${encodeURIComponent(vehiclesState.query || '')}&district=${encodeURIComponent(vehiclesState.district || '')}`),
            fetch('/api/tn-dashboard-stats?page=1&page_size=1'),
        ]);

        const lorries = await lorriesRes.json();
        const districtsData = await districtsRes.json();

        renderVehiclesTable(lorries.items || []);
        renderVehiclesPagination(lorries);
        renderDistrictSelect(districtsData.districts || []);
    } catch (error) {
        const body = document.getElementById('vehiclesTableBody');
        if (body) body.innerHTML = '<tr><td colspan="12">Unable to load vehicles right now.</td></tr>';
    } finally {
        vehiclesRefreshInFlight = false;
        if (vehiclesRefreshQueued) {
            vehiclesRefreshQueued = false;
            refreshVehicles();
        }
    }
}

const vehiclesSearchInput = document.getElementById('vehiclesSearchInput');
const vehiclesDistrictSelect = document.getElementById('vehiclesDistrictSelect');
const vehiclesSearchApplyBtn = document.getElementById('vehiclesSearchApplyBtn');
const vehiclesSearchClearBtn = document.getElementById('vehiclesSearchClearBtn');

if (vehiclesSearchApplyBtn) {
    vehiclesSearchApplyBtn.addEventListener('click', () => {
        vehiclesState.query = vehiclesSearchInput ? vehiclesSearchInput.value.trim() : '';
        vehiclesState.district = vehiclesDistrictSelect ? vehiclesDistrictSelect.value || '' : '';
        vehiclesState.page = 1;
        refreshVehicles();
    });
}

if (vehiclesSearchClearBtn) {
    vehiclesSearchClearBtn.addEventListener('click', () => {
        vehiclesState.query = '';
        vehiclesState.district = '';
        vehiclesState.page = 1;
        if (vehiclesSearchInput) vehiclesSearchInput.value = '';
        if (vehiclesDistrictSelect) vehiclesDistrictSelect.value = '';
        refreshVehicles();
    });
}

if (vehiclesDistrictSelect) {
    vehiclesDistrictSelect.addEventListener('change', () => {
        vehiclesState.district = vehiclesDistrictSelect.value || '';
        vehiclesState.page = 1;
        refreshVehicles();
    });
}

refreshVehicles();
setInterval(refreshVehicles, 6000);

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
