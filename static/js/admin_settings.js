// static/js/admin_settings.js
document.addEventListener('DOMContentLoaded', () => {
    const settingsForm = document.getElementById('settings-form');
    const runFreshserviceBtn = document.getElementById('run-freshservice');
    const runDattoBtn = document.getElementById('run-datto');

    settingsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const settings = {
            FRESHSERVICE_PULL_INTERVAL: document.getElementById('freshservice-interval').value,
            DATTO_PULL_INTERVAL: document.getElementById('datto-interval').value
        };

        const response = await fetch('/api/admin/save_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        const result = await response.json();
        if (result.success) {
            alert('Settings saved successfully!');
        } else {
            alert(`An error occurred: ${result.error}`);
        }
    });

    runFreshserviceBtn.addEventListener('click', async () => {
        const response = await fetch('/api/admin/run_job/freshservice', { method: 'POST' });
        const result = await response.json();
        alert(result.message || result.error);
    });

    runDattoBtn.addEventListener('click', async () => {
        const response = await fetch('/api/admin/run_job/datto', { method: 'POST' });
        const result = await response.json();
        alert(result.message || result.error);
    });
});
