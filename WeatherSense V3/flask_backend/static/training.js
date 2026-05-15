/**
 * Training page - one-click sensor log training and CSV upload training.
 * Shows validation feedback and loading indicators.
 */

const resultEl = document.getElementById('train-result');

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function showResult(html) {
    resultEl.innerHTML = html;
    resultEl.style.display = 'block';
}

function setLoading(btn, loading) {
    if (!btn) return;
    const text = btn.querySelector('.btn-text');
    const load = btn.querySelector('.btn-loading');
    if (text && load) {
        text.hidden = loading;
        load.hidden = !loading;
    }
    btn.disabled = loading;
}

function showStats(stats) {
    if (!stats) return '';
    let html = '<div class="card train-stats-card">';
    html += '<h3 class="card-title">Training Stats</h3>';
    html += '<p><strong>Rows used:</strong> ' + (stats.rows_used || 0) + '</p>';
    if (stats.class_distribution) {
        html += '<p><strong>Class distribution:</strong></p><ul class="stats-list">';
        for (const [k, v] of Object.entries(stats.class_distribution)) {
            html += '<li><span>' + escapeHtml(k) + '</span><strong>' + escapeHtml(v) + '</strong></li>';
        }
        html += '</ul>';
    }
    html += '<p><strong>Classifier:</strong> ' + (stats.classifier_trained ? 'Ready' : 'Not ready') + ' | <strong>Forecast:</strong> ' + (stats.forecast_trained ? 'Ready' : 'Not ready') + '</p>';
    html += '</div>';
    return html;
}

function showValidationFeedback(data) {
    let html = '';
    if (data.rows_used != null) {
        html += '<p><strong>Rows used:</strong> ' + escapeHtml(data.rows_used) + '</p>';
    }
    if (data.rows_skipped != null && data.rows_skipped > 0) {
        html += '<p><strong>Rows skipped:</strong> ' + escapeHtml(data.rows_skipped) + '</p>';
    }
    if (data.missing_columns && data.missing_columns.length > 0) {
        html += '<p><strong>Missing columns:</strong> ' + data.missing_columns.map(escapeHtml).join(', ') + '</p>';
    }
    return html;
}

document.getElementById('form-csv').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById('csv-file');
    const file = fileInput.files[0];
    const btn = document.getElementById('btn-csv');
    if (!file) {
        showResult('<div class="alert alert-error">Please select a file</div>');
        return;
    }
    const ext = (file.name || '').toLowerCase();
    if (!ext.endsWith('.csv')) {
        showResult('<div class="alert alert-error">Invalid file type. Only CSV files are accepted.</div>');
        return;
    }
    const balanced = document.getElementById('balanced-csv').checked;
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    params.set('balanced', balanced ? '1' : '0');
    showResult('<div class="alert alert-info">Training from CSV dataset...</div>');
    setLoading(btn, true);
    try {
        const res = await fetch('/api/train?' + params.toString(), {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            let feedback = '<div class="alert alert-success">' + escapeHtml(data.message) + '</div>';
            feedback += showValidationFeedback({
                rows_used: data.rows_used,
                rows_skipped: data.rows_skipped,
                missing_columns: data.missing_columns || []
            });
            feedback += showStats(data.stats);
            showResult(feedback);
            window.dispatchEvent(new CustomEvent('modelsRetrained'));
        } else {
            let errHtml = '<div class="alert alert-error">' + escapeHtml(data.error || 'Training failed') + '</div>';
            if (data.missing_columns && data.missing_columns.length) {
                errHtml += '<p><strong>Missing columns:</strong> ' + data.missing_columns.map(escapeHtml).join(', ') + '</p>';
            }
            if (data.rows_skipped != null) {
                errHtml += '<p>Rows skipped: ' + escapeHtml(data.rows_skipped) + '</p>';
            }
            showResult(errHtml);
        }
    } catch (err) {
        showResult('<div class="alert alert-error">Error: ' + escapeHtml(err.message) + '</div>');
    } finally {
        setLoading(btn, false);
    }
});

document.getElementById('form-sqlite').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-sqlite');
    const balanced = document.getElementById('balanced-sqlite').checked;
    const params = new URLSearchParams();
    params.set('balanced', balanced ? '1' : '0');
    showResult('<div class="alert alert-info">Training from saved sensor logs...</div>');
    setLoading(btn, true);
    try {
        const res = await fetch('/api/train_sqlite?' + params.toString(), { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showResult('<div class="alert alert-success">' + escapeHtml(data.message) + '</div>' + showStats(data.stats));
            window.dispatchEvent(new CustomEvent('modelsRetrained'));
        } else {
            showResult('<div class="alert alert-error">' + escapeHtml(data.error || 'Training failed') + '</div>');
        }
    } catch (err) {
        showResult('<div class="alert alert-error">Error: ' + escapeHtml(err.message) + '</div>');
    } finally {
        setLoading(btn, false);
    }
});
