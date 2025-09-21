// static/js/admin.js
document.addEventListener('DOMContentLoaded', () => {
    const reinitDbBtn = document.getElementById('reinit-db-btn');

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
});
