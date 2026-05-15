/**
 * Sensor Logs page - preview last 50 rows and manage collected sensor data.
 */

const actionMessageEl = document.getElementById('logs-action-message');
const deleteLogsBtn = document.getElementById('btn-delete-logs');

function showActionMessage(message, type = 'info') {
    if (!actionMessageEl) return;
    actionMessageEl.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
}

async function loadPreview() {
    const msg = document.getElementById('preview-message');
    const table = document.getElementById('preview-table');
    const tbody = document.getElementById('preview-tbody');

    try {
        msg.hidden = false;
        msg.textContent = 'Loading...';
        msg.className = 'alert alert-info';

        const res = await fetch('/api/dataset_preview?n=50');
        const data = await res.json();

        if (!data.rows || data.rows.length === 0) {
            msg.textContent = 'No sensor logs in database yet.';
            msg.className = 'alert alert-info';
            table.hidden = true;
            tbody.innerHTML = '';
            return;
        }

        msg.hidden = true;
        table.hidden = false;
        tbody.innerHTML = data.rows.map(r => `
            <tr>
                <td>${r.id}</td>
                <td>${r.timestamp || '--'}</td>
                <td>${r.temperature != null ? r.temperature.toFixed(1) : '--'}</td>
                <td>${r.humidity != null ? r.humidity.toFixed(1) : '--'}</td>
                <td>${r.pressure != null ? r.pressure.toFixed(1) : '--'}</td>
                <td>${r.rain ? 'Yes' : 'No'}</td>
            </tr>
        `).join('');
    } catch (e) {
        msg.hidden = false;
        msg.textContent = 'Failed to load sensor logs: ' + e.message;
        msg.className = 'alert alert-error';
    }
}

async function deleteSensorLogs() {
    const confirmed = window.confirm('Delete all collected sensor data from the database? This cannot be undone.');
    if (!confirmed) return;

    if (deleteLogsBtn) {
        deleteLogsBtn.disabled = true;
        deleteLogsBtn.innerHTML = '<span class="btn-icon" aria-hidden="true">!</span>Deleting...';
    }

    try {
        const res = await fetch('/api/sensor_logs', { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            throw new Error(data.error || 'Delete failed');
        }

        showActionMessage(`Deleted ${data.deleted || 0} collected sensor log${data.deleted === 1 ? '' : 's'}.`, 'success');
        await loadPreview();
    } catch (e) {
        showActionMessage('Failed to delete sensor logs: ' + e.message, 'error');
    } finally {
        if (deleteLogsBtn) {
            deleteLogsBtn.disabled = false;
            deleteLogsBtn.innerHTML = '<span class="btn-icon" aria-hidden="true">!</span>Delete Sensor Data';
        }
    }
}

if (deleteLogsBtn) {
    deleteLogsBtn.addEventListener('click', deleteSensorLogs);
}

loadPreview();

// Listen for real-time updates from the server
const evtSource = new EventSource('/api/stream');
evtSource.onmessage = function(event) {
    if (event.data === 'update') {
        loadPreview();
    }
};
