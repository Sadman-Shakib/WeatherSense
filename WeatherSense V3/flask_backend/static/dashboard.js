/**
 * Dashboard - real-time updates via Fetch API.
 * Polls /api/latest, /api/forecast, /api/chart/24h every 10 seconds.
 */

const POLL_INTERVAL_MS = 10000;

const tempEl = document.getElementById('temp');
const humEl = document.getElementById('hum');
const presEl = document.getElementById('pres');
const rainEl = document.getElementById('rain');
const classificationEl = document.getElementById('classification');
const classificationCardEl = document.getElementById('classification-card');
const classificationNoteEl = document.getElementById('classification-note');

const forecastEls = {
    temperature: document.getElementById('forecast-temperature'),
    humidity: document.getElementById('forecast-humidity'),
    pressure: document.getElementById('forecast-pressure')
};

const charts = {};

const classificationNotes = {
    sunny: 'Sunny conditions detected.',
    cloudy: 'Cloudy conditions detected.',
    rainy: 'Rain conditions detected.',
    unknown: 'Waiting for model reading.'
};

function formatNumber(value, digits = 1) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : '--';
}

function formatHour(value) {
    const hour = Number(value);
    return Number.isFinite(hour) ? `+${hour}h` : '+--h';
}

function normalizeWeather(value) {
    const normalized = String(value || 'unknown')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '');

    return normalized || 'unknown';
}

async function fetchLatest() {
    try {
        const res = await fetch('/api/latest');
        const data = await res.json();

        if (data.readings) {
            const r = data.readings;
            tempEl.textContent = formatNumber(r.temperature);
            humEl.textContent = formatNumber(r.humidity);
            presEl.textContent = formatNumber(r.pressure);
            rainEl.textContent = r.rain ? 'Yes' : 'No';
            rainEl.className = r.rain ? 'tile-value rain-value rain-active' : 'tile-value rain-value rain-clear';
        }

        if (data.classification) {
            const weatherClass = normalizeWeather(data.classification);
            classificationEl.textContent = data.classification;
            classificationEl.className = `weather-badge badge badge-${weatherClass}`;
            classificationCardEl.className = `classification-display weather-${weatherClass}`;
            classificationNoteEl.textContent = classificationNotes[weatherClass] || classificationNotes.unknown;
        }
    } catch (e) {
        console.error('fetchLatest error', e);
    }
}

function renderForecastMetric(container, forecast, key, unit, digits = 1) {
    if (!container) return;

    container.innerHTML = forecast.map((item) => `
        <article class="forecast-pill">
            <span class="forecast-hour">${formatHour(item.hour)}</span>
            <strong>${formatNumber(item[key], digits)}<span>${unit}</span></strong>
        </article>
    `).join('');
}

function showForecastEmpty() {
    Object.values(forecastEls).forEach((container) => {
        if (container) {
            container.innerHTML = '<p class="empty-state">Insufficient data for forecast</p>';
        }
    });
}

async function fetchForecast() {
    try {
        const res = await fetch('/api/forecast');
        const data = await res.json();

        if (data.forecast && data.forecast.length) {
            renderForecastMetric(forecastEls.temperature, data.forecast, 'temperature', '\u00b0C');
            renderForecastMetric(forecastEls.humidity, data.forecast, 'humidity', '%');
            renderForecastMetric(forecastEls.pressure, data.forecast, 'pressure', 'hPa');
        } else {
            showForecastEmpty();
        }
    } catch (e) {
        console.error('fetchForecast error', e);
        showForecastEmpty();
    }
}

async function fetchChart() {
    try {
        const res = await fetch('/api/chart/24h');
        const data = await res.json();

        if (data.labels && data.labels.length) {
            updateCharts(data);
        }
    } catch (e) {
        console.error('fetchChart error', e);
    }
}

function renderLineChart(key, canvasId, labels, values, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return;

    if (charts[key]) {
        charts[key].destroy();
    }

    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 260);
    gradient.addColorStop(0, config.fillStart);
    gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');

    charts[key] = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: config.label,
                data: values || [],
                borderColor: config.color,
                backgroundColor: gradient,
                borderWidth: 3,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: config.color,
                pointHoverBorderColor: '#ffffff',
                pointHoverBorderWidth: 2,
                tension: 0.35,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#111a22',
                    borderColor: 'rgba(255, 255, 255, 0.16)',
                    borderWidth: 1,
                    padding: 12,
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    displayColors: false
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    border: {
                        display: false
                    },
                    grid: {
                        color: 'rgba(154, 168, 181, 0.12)'
                    },
                    ticks: {
                        color: '#9aa8b5',
                        maxTicksLimit: 5
                    }
                },
                x: {
                    border: {
                        display: false
                    },
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#9aa8b5',
                        maxTicksLimit: 8
                    }
                }
            }
        }
    });
}

function updateCharts(data) {
    renderLineChart('temperature', 'chartTemperature', data.labels, data.temperature, {
        label: 'Temperature (\u00b0C)',
        color: '#f97316',
        fillStart: 'rgba(249, 115, 22, 0.24)'
    });

    renderLineChart('humidity', 'chartHumidity', data.labels, data.humidity, {
        label: 'Humidity (%)',
        color: '#0ea5e9',
        fillStart: 'rgba(14, 165, 233, 0.22)'
    });

    renderLineChart('pressure', 'chartPressure', data.labels, data.pressure, {
        label: 'Air Pressure (hPa)',
        color: '#16a34a',
        fillStart: 'rgba(22, 163, 74, 0.2)'
    });
}

function poll() {
    fetchLatest();
    fetchForecast();
    fetchChart();
}

poll();
// Listen for real-time updates from the server
const evtSource = new EventSource('/api/stream');
evtSource.onmessage = function(event) {
    if (event.data === 'update') {
        poll();
    }
};

window.addEventListener('modelsRetrained', () => {
    poll();
});
