let dbChart = null;

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function renderAlignmentChart(summary) {
    const canvas = document.getElementById('dbAlignChart');
    if (!canvas) return;

    const profiles = ['safe', 'normal', 'high_risk'];
    const risky = profiles.map(p => Number(summary?.[p]?.risky || 0));
    const aligned = profiles.map(p => Number(summary?.[p]?.aligned || 0));

    if (dbChart) dbChart.destroy();
    dbChart = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: profiles,
            datasets: [
                { label: 'Risky', data: risky, backgroundColor: 'rgba(239,68,68,0.55)' },
                { label: 'Aligned', data: aligned, backgroundColor: 'rgba(34,197,94,0.55)' },
            ],
        },
        options: { responsive: true },
    });
}

function renderMisalignedRows(rows) {
    const body = document.getElementById('dbMisalignedBody');
    if (!body) return;

    if (!rows || !rows.length) {
        body.innerHTML = '<tr><td colspan="8">All driver behavior rows are aligned with profile risk.</td></tr>';
        return;
    }

    body.innerHTML = rows.map(item => `
        <tr>
            <td>${item.vehicle_id}</td>
            <td>${item.profile}</td>
            <td>${Number(item.risk || 0).toFixed(1)}</td>
            <td>${item.harsh_braking || 0}</td>
            <td>${Number(item.speed_fluctuation || 0).toFixed(2)}</td>
            <td>${item.risky ? 'YES' : 'NO'}</td>
            <td>${item.expected_risky ? 'YES' : 'NO'}</td>
            <td>${Number(item.final_threat_score || 0).toFixed(1)}</td>
        </tr>
    `).join('');
}

async function refreshDriverBehaviorPage() {
    try {
        const response = await fetch('/api/driver-behavior');
        const data = await response.json();
        const summary = data.summary || {};

        setText('dbSafeCount', summary.safe?.count || 0);
        setText('dbNormalCount', summary.normal?.count || 0);
        setText('dbHighRiskCount', summary.high_risk?.count || 0);
        setText('dbMisaligned', (data.misaligned || []).length);

        renderAlignmentChart(summary);
        renderMisalignedRows(data.misaligned || []);
    } catch (_error) {
        const body = document.getElementById('dbMisalignedBody');
        if (body) body.innerHTML = '<tr><td colspan="8">Unable to load driver behavior data.</td></tr>';
    }
}

refreshDriverBehaviorPage();
setInterval(refreshDriverBehaviorPage, 7000);
