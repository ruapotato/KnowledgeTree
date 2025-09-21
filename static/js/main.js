// static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('file-browser')) {
        initIndexPage();
    }
    if (document.querySelector('.view-container')) {
        initViewPage();
    }
});

// --- File Manager (Index Page) Logic ---
function initIndexPage() {
    const fileBrowser = document.getElementById('file-browser');
    const breadcrumb = document.getElementById('breadcrumb');
    const contextMenu = document.getElementById('context-menu');
    const backBtn = document.getElementById('back-btn');
    
    let currentFolderId = 'root';
    let currentFolderIsAttached = false;
    let selectedItemId = null;
    let selectedItemType = { is_folder: false, is_attached: false };

    async function navigateTo(folderId, fromHistory = false) {
        currentFolderId = folderId;
        selectedItemId = null;

        // Update URL unless we are navigating from a history event (popstate)
        if (!fromHistory) {
            history.pushState({ folderId: folderId }, "", `/#/${folderId}`);
        }
        
        const response = await fetch(`/api/node/${folderId}`);
        const data = await response.json();
        currentFolderIsAttached = data.is_attached || false;
        
        // Disable back button if at root
        backBtn.disabled = (folderId === 'root');

        await Promise.all([
            renderItems(folderId),
            renderBreadcrumb(folderId)
        ]);
    }

    async function renderItems(folderId) {
        const response = await fetch(`/api/nodes/${folderId}`);
        const items = await response.json();
        
        fileBrowser.innerHTML = '';
        items.forEach(item => {
            const itemEl = document.createElement('div');
            itemEl.className = 'file-item';
            itemEl.dataset.id = item.id;
            itemEl.dataset.isFolder = item.is_folder;
            itemEl.dataset.isAttached = item.is_attached || false;
            
            let iconClass = 'fas fa-file-alt';
            if (item.is_folder) {
                iconClass = item.is_attached ? 'fas fa-paperclip' : 'fas fa-folder';
            }
            
            itemEl.innerHTML = `<i class="${iconClass}"></i><span class="name">${item.name}</span>`;
            
            itemEl.addEventListener('click', () => {
                document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
                itemEl.classList.add('selected');
                selectedItemId = item.id;
                selectedItemType = { 
                    is_folder: item.is_folder, 
                    is_attached: item.is_attached || false 
                };
            });

            itemEl.addEventListener('dblclick', () => {
                if (item.is_folder) {
                    navigateTo(item.id);
                } else {
                    window.location.href = `/view/${item.id}`;
                }
            });

            fileBrowser.appendChild(itemEl);
        });
    }

    async function renderBreadcrumb(folderId) {
        const response = await fetch(`/api/path/${folderId}`);
        const path = await response.json();

        breadcrumb.innerHTML = '';
        path.forEach((segment, index) => {
            if (index < path.length - 1) {
                const link = document.createElement('a');
                link.href = `/#/${segment.id}`;
                link.textContent = segment.name;
                link.onclick = (e) => { e.preventDefault(); navigateTo(segment.id); };
                breadcrumb.appendChild(link);
                breadcrumb.appendChild(document.createElement('span')).textContent = '>';
            } else {
                breadcrumb.appendChild(document.createTextNode(` ${segment.name}`));
            }
        });
    }

    function showContextMenu(e) {
        e.preventDefault();
        contextMenu.style.display = 'block';
        contextMenu.style.left = `${e.pageX}px`;
        contextMenu.style.top = `${e.pageY}px`;

        const targetItem = e.target.closest('.file-item');
        const [openEl, renameEl, deleteEl, newFolderEl, newAttachedEl, newArticleEl] = [
            'context-open', 'context-rename', 'context-delete', 'context-new-folder', 
            'context-new-attached', 'context-new-article'
        ].map(id => document.getElementById(id));

        [openEl, renameEl, deleteEl, newFolderEl, newAttachedEl, newArticleEl].forEach(el => el.classList.remove('hidden'));

        if (targetItem) {
            targetItem.click();
        } else {
            selectedItemId = null;
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
            [openEl, renameEl, deleteEl].forEach(el => el.classList.add('hidden'));
        }

        if (currentFolderIsAttached) {
            // Can't create a *regular* folder inside an attached one
            newFolderEl.classList.add('hidden');
        }
    }

    document.getElementById('file-browser-container').addEventListener('contextmenu', showContextMenu);
    document.addEventListener('click', () => contextMenu.style.display = 'none');

    async function createNewItem(isFolder, isAttached = false) {
        const type = isAttached ? 'attached folder' : (isFolder ? 'folder' : 'knowledge');
        const name = prompt(`Enter name for new ${type}:`);
        if (name) {
            const response = await fetch('/api/node', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, parent_id: currentFolderId, is_folder: isFolder, is_attached: isAttached })
            });
            if (!response.ok) {
                const error = await response.json();
                alert(`Error: ${error.error}`);
            }
            renderItems(currentFolderId);
        }
    }

    async function renameItem() {
        if (!selectedItemId) return;
        const currentName = document.querySelector(`.file-item[data-id="${selectedItemId}"] .name`).textContent;
        const newName = prompt("Enter new name:", currentName);
        if (newName && newName !== currentName) {
            await fetch(`/api/node/${selectedItemId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
            renderItems(currentFolderId);
        }
    }

    async function deleteItem() {
        if (!selectedItemId) return;
        if (confirm("Are you sure you want to delete this item and all its contents?")) {
            await fetch(`/api/node/${selectedItemId}`, { method: 'DELETE' });
            renderItems(currentFolderId);
        }
    }
    
    document.getElementById('context-new-folder').onclick = () => createNewItem(true, false);
    document.getElementById('context-new-attached').onclick = () => createNewItem(true, true);
    document.getElementById('context-new-article').onclick = () => createNewItem(false, false);
    document.getElementById('context-rename').onclick = renameItem;
    document.getElementById('context-delete').onclick = deleteItem;
    document.getElementById('context-open').onclick = () => {
        if (selectedItemId) {
            if (selectedItemType.is_folder) navigateTo(selectedItemId);
            else window.location.href = `/view/${selectedItemId}`;
        }
    };

    // Navigation Logic
    backBtn.addEventListener('click', () => history.back());
    window.addEventListener('popstate', (e) => {
        if (e.state && e.state.folderId) {
            navigateTo(e.state.folderId, true);
        }
    });

    // Initial Load from URL
    const initialFolderId = window.location.hash.substring(2) || 'root';
    navigateTo(initialFolderId, true);
    history.replaceState({ folderId: initialFolderId }, "", `/#/${initialFolderId}`);
}

// --- View Page Logic ---
function initViewPage() {
    const nodeNameEl = document.getElementById('node-name');
    const contentDisplayEl = document.getElementById('content-display');
    const saveBtn = document.getElementById('save-btn');
    const exportBtn = document.getElementById('export-context-btn');
    const uploadBtn = document.getElementById('upload-btn');
    const fileListEl = document.getElementById('file-list');

    const mde = new EasyMDE({ element: document.getElementById('markdown-editor') });

    async function loadNodeData() {
        const response = await fetch(`/api/node/${NODE_ID}`);
        const data = await response.json();

        nodeNameEl.textContent = data.name;
        contentDisplayEl.innerHTML = data.content_html || '<p>No content yet. Click Edit to add some.</p>';
        mde.value(data.content || '');

        if (data.is_folder) {
            document.body.classList.add('is-folder');
        }

        // Display files
        fileListEl.innerHTML = '';
        if (data.files && data.files.length > 0) {
            const ul = document.createElement('ul');
            data.files.forEach(file => {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.href = `/uploads/${file.filename}`;
                a.textContent = file.filename;
                a.target = '_blank';
                li.appendChild(a);
                ul.appendChild(li);
            });
            fileListEl.appendChild(ul);
        } else {
            fileListEl.innerHTML = '<p>No files attached.</p>';
        }
    }

    saveBtn.addEventListener('click', async () => {
        await fetch(`/api/node/${NODE_ID}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: mde.value() })
        });
        alert('Content saved!');
        loadNodeData(); // Refresh displayed content
    });

    exportBtn.addEventListener('click', async () => {
        const response = await fetch(`/api/context/${NODE_ID}`);
        const data = await response.json();
        try {
            await navigator.clipboard.writeText(data.context);
            exportBtn.textContent = 'Copied!';
            setTimeout(() => { exportBtn.innerHTML = '<i class="fas fa-copy"></i> Export Full Context'; }, 2000);
        } catch (err) {
            console.error('Failed to copy text: ', err);
            alert('Failed to copy context.');
        }
    });

    uploadBtn.addEventListener('click', async () => {
        const fileInput = document.getElementById('file-upload-input');
        if (fileInput.files.length === 0) {
            alert('Please select a file to upload.');
            return;
        }
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        const response = await fetch(`/api/upload/${NODE_ID}`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            alert('File uploaded successfully!');
            fileInput.value = ''; // Clear the input
            loadNodeData(); // Refresh the file list
        } else {
            alert('File upload failed.');
        }
    });

    loadNodeData();
}
