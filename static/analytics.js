let riskChart = null;
let violationChart = null;

function smoothSeries(values, windowSize = 3) {
    return values.map((_, index) => {
        const start = Math.max(0, index - windowSize + 1);
        const slice = values.slice(start, index + 1).filter(v => typeof v === 'number');
        if (!slice.length) return null;
        return slice.reduce((a, b) => a + b, 0) / slice.length;
    });
}

async function renderRiskHistory() {
    const res = await fetch('/api/history/risk?minutes=240');
    const data = await res.json();
    const canvas = document.getElementById('analyticsRiskChart');
    if (!canvas) return;

    const labelsSet = new Set();
    Object.values(data).forEach(points => {
        points.slice(-90).forEach(p => labelsSet.add(new Date(p.ts).toLocaleTimeString()));
    });
    const labels = Array.from(labelsSet).slice(-60);

    const palette = ['#4285f4', '#ea4335', '#fbbc05', '#34a853', '#7baaf7', '#f28b82'];
    const datasets = Object.entries(data).map(([vehicleId, points], index) => {
        const pointMap = new Map(points.slice(-120).map(p => [new Date(p.ts).toLocaleTimeString(), Number(p.risk || 0)]));
        const raw = labels.map(label => pointMap.has(label) ? pointMap.get(label) : null);
        const smooth = smoothSeries(raw, 4);
        return {
            label: `${vehicleId} (smoothed)`,
            data: smooth,
            borderColor: palette[index % palette.length],
            backgroundColor: palette[index % palette.length],
            fill: false,
            spanGaps: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
        };
    });

    if (!datasets.length) return;

    if (riskChart) {
        riskChart.destroy();
    }

    riskChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            scales: {
                x: { ticks: { maxTicksLimit: 10 } },
                y: { min: 0, max: 100 },
            },
            plugins: { legend: { display: true } },
        },
    });
}

async function renderViolationRate() {
    const res = await fetch('/api/history/violation-rate?minutes=240&bucket_minutes=5');
    const rows = await res.json();
    const canvas = document.getElementById('violationRateChart');
    if (!canvas) return;

    const labels = rows.map(row => new Date(row.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    const total = rows.map(row => Number(row.total || 0));
    const critical = rows.map(row => Number(row.critical || 0));

    if (violationChart) {
        violationChart.destroy();
    }

    violationChart = new Chart(canvas.getContext('2d'), {
        data: {
            labels,
            datasets: [
                {
                    type: 'bar',
                    label: 'Total Violations',
                    data: total,
                    backgroundColor: 'rgba(66, 133, 244, 0.35)',
                    borderColor: '#4285f4',
                    borderWidth: 1,
                },
                {
                    type: 'line',
                    label: 'Critical Violations',
                    data: critical,
                    borderColor: '#d93025',
                    backgroundColor: '#d93025',
                    fill: false,
                    tension: 0.25,
                    pointRadius: 2,
                },
            ],
        },
        options: {
            responsive: true,
            scales: {
                x: { ticks: { maxTicksLimit: 12 } },
                y: { beginAtZero: true },
            },
        },
    });
}

async function loadAnalytics() {
    await Promise.all([renderRiskHistory(), renderViolationRate()]);
}

loadAnalytics();
setInterval(loadAnalytics, 10000);
