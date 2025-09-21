// static/js/admin.js
document.addEventListener('DOMContentLoaded', () => {
    const reinitDbBtn = document.getElementById('reinit-db-btn');
    const settingsForm = document.getElementById('settings-form');
    const runFreshserviceBtn = document.getElementById('run-freshservice');
    const runDattoBtn = document.getElementById('run-datto');
    const exportBtn = document.getElementById('export-data-btn');
    const importBtn = document.getElementById('import-data-btn');
    const importFileInput = document.getElementById('import-file-input');

    if (reinitDbBtn) {
        reinitDbBtn.addEventListener('click', async () => {
            const confirmation = prompt('This is a destructive action that cannot be undone. To confirm, type "DELETE" in the box below:');
            
            if (confirmation === 'DELETE') {
                try {
                    const response = await fetch('/api/admin/reinitialize_db', {
                        method: 'POST',
                    });

                    const result = await response.json();

                    if (result.success) {
                        alert('Success! The database has been wiped and re-initialized. You will be redirected to the home page.');
                        window.location.href = '/';
                    } else {
                        alert(`An error occurred: ${result.error}`);
                    }
                } catch (error) {
                    alert(`A network error occurred: ${error}`);
                }
            } else {
                alert('Action cancelled. You did not type "DELETE".');
            }
        });
    }

    if (settingsForm) {
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
    }

    if (runFreshserviceBtn) {
        runFreshserviceBtn.addEventListener('click', async () => {
            runFreshserviceBtn.disabled = true;
            runFreshserviceBtn.textContent = 'Syncing...';
            const response = await fetch('/api/admin/run_job/freshservice', { method: 'POST' });
            const result = await response.json();
            alert(result.message || result.error);
            runFreshserviceBtn.disabled = false;
            runFreshserviceBtn.innerHTML = '<i class="fas fa-sync"></i> Run Freshservice Sync';
        });
    }

    if (runDattoBtn) {
        runDattoBtn.addEventListener('click', async () => {
            runDattoBtn.disabled = true;
            runDattoBtn.textContent = 'Syncing...';
            const response = await fetch('/api/admin/run_job/datto', { method: 'POST' });
            const result = await response.json();
            alert(result.message || result.error);
            runDattoBtn.disabled = false;
            runDattoBtn.innerHTML = '<i class="fas fa-sync"></i> Run Datto RMM Sync';
        });
    }

    if (exportBtn) {
        exportBtn.addEventListener('click', async () => {
            window.location.href = '/api/admin/export';
        });
    }

    if (importBtn) {
        importBtn.addEventListener('click', async () => {
            const file = importFileInput.files[0];
            if (!file) {
                alert('Please select a file to import.');
                return;
            }
            const confirmation = confirm('Are you sure you want to import this data? This may overwrite existing user-created content.');
            if (!confirmation) {
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            
            importBtn.disabled = true;
            importBtn.textContent = 'Importing...';

            const response = await fetch('/api/admin/import', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();
            if (result.success) {
                alert('Import successful!');
            } else {
                alert(`An error occurred: ${result.error}`);
            }
            
            importBtn.disabled = false;
            importBtn.textContent = 'Import User Data';
        });
    }
});
