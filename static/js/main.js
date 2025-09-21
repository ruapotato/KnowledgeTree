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
    // This entire function is correct and unchanged
    const fileBrowser = document.getElementById('file-browser');
    const breadcrumbNav = document.getElementById('breadcrumb');
    const contextMenu = document.getElementById('context-menu');
    const backBtn = document.getElementById('back-btn');
    
    let currentFolderId = null;
    let currentPathArray = [];
    let currentFolderIsAttached = false;
    let selectedItemId = null;
    let selectedItemType = { is_folder: false, is_attached: false };

    async function navigateToPath(pathArray, fromHistory = false) {
        let nodeId = 'root';
        if (pathArray && pathArray.length > 0) {
            const response = await fetch('/api/resolve_path', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: pathArray })
            });
            if (!response.ok) {
                console.error("Path not found, redirecting to root.");
                navigateToPath([], fromHistory);
                return;
            }
            const data = await response.json();
            nodeId = data.id;
        }

        currentFolderId = nodeId;
        selectedItemId = null;
        currentPathArray = pathArray || [];

        if (!fromHistory) {
            const urlPath = currentPathArray.map(p => encodeURIComponent(p)).join('/');
            history.pushState({ path: currentPathArray }, "", `/#/${urlPath}`);
        }
        
        const nodeDataResponse = await fetch(`/api/node/${nodeId}`);
        const nodeData = await nodeDataResponse.json();
        currentFolderIsAttached = nodeData.is_attached || false;
        
        backBtn.disabled = (currentPathArray.length === 0);

        await Promise.all([
            renderItems(nodeId),
            renderBreadcrumb(nodeId)
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
                selectedItemType = { is_folder: item.is_folder, is_attached: item.is_attached || false };
            });

            itemEl.addEventListener('dblclick', () => {
                if (item.is_folder) {
                    const newPath = [...currentPathArray, item.name];
                    navigateToPath(newPath);
                } else {
                    window.location.href = `/view/${item.id}`;
                }
            });

            fileBrowser.appendChild(itemEl);
        });
    }
    
    async function renderBreadcrumb(folderId) {
        const response = await fetch(`/api/path/${folderId}`);
        const pathData = await response.json();

        breadcrumbNav.innerHTML = '';
        pathData.forEach((segment, index) => {
            const pathSlice = pathData.slice(1, index + 1).map(p => p.name);
            
            if (index < pathData.length - 1) {
                const link = document.createElement('a');
                link.href = '#';
                link.textContent = segment.name;
                link.onclick = (e) => { e.preventDefault(); navigateToPath(pathSlice); };
                breadcrumbNav.appendChild(link);
                breadcrumbNav.appendChild(document.createElement('span')).textContent = '>';
            } else {
                breadcrumbNav.appendChild(document.createTextNode(` ${segment.name}`));
            }
        });
    }

    function showContextMenu(e) {
        e.preventDefault();
        const targetItem = e.target.closest('.file-item');
        
        contextMenu.style.display = 'none';

        if (targetItem) {
            targetItem.click();
        } else {
            selectedItemId = null;
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
        }
        
        contextMenu.style.display = 'block';
        contextMenu.style.left = `${e.pageX}px`;
        contextMenu.style.top = `${e.pageY}px`;

        const [openEl, renameEl, deleteEl, newFolderEl, newAttachedEl, newArticleEl] = [
            'context-open', 'context-rename', 'context-delete', 'context-new-folder', 
            'context-new-attached', 'context-new-article'
        ].map(id => document.getElementById(id));
        
        [openEl, renameEl, deleteEl, newFolderEl, newAttachedEl, newArticleEl].forEach(el => el.classList.remove('hidden'));

        if (!selectedItemId) {
            [openEl, renameEl, deleteEl].forEach(el => el.classList.add('hidden'));
        }
        
        if (currentFolderIsAttached) {
            newFolderEl.classList.add('hidden');
        }
    }
    
    document.getElementById('file-browser-container').addEventListener('contextmenu', showContextMenu);
    document.addEventListener('click', (e) => {
        if (!contextMenu.contains(e.target)) {
            contextMenu.style.display = 'none';
        }
    });
    
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
            if (selectedItemType.is_folder) {
                const itemName = document.querySelector(`.file-item[data-id="${selectedItemId}"] .name`).textContent;
                const newPath = [...currentPathArray, itemName];
                navigateToPath(newPath);
            }
            else window.location.href = `/view/${selectedItemId}`;
        }
    };

    backBtn.addEventListener('click', () => history.back());
    window.addEventListener('popstate', (e) => {
        if (e.state && e.state.path) {
            navigateToPath(e.state.path, true);
        }
    });

    const initialPath = window.location.hash.substring(2).split('/').filter(p => p).map(p => decodeURIComponent(p));
    navigateToPath(initialPath, true);
    history.replaceState({ path: initialPath }, "", `/#/${initialPath.map(p=>encodeURIComponent(p)).join('/')}`);
}


// --- View Page Logic ---
function initViewPage() {
    const nodeNameEl = document.getElementById('node-name');
    const contentDisplayEl = document.getElementById('content-display');
    const saveBtn = document.getElementById('save-btn');
    const exportBtn = document.getElementById('export-context-btn');
    const uploadBtn = document.getElementById('upload-btn');
    const fileListEl = document.getElementById('file-list');

    // **NEW**: Initialize Toast UI Editor
    const editor = new toastui.Editor({
        el: document.querySelector('#editor'),
        height: '600px',
        initialEditType: 'wysiwyg', // Start in rich-text mode
        previewStyle: 'tab',
        usageStatistics: false // Disables data collection
    });

    async function loadNodeData() {
        const response = await fetch(`/api/node/${NODE_ID}`);
        const data = await response.json();
        
        nodeNameEl.textContent = data.name;
        contentDisplayEl.innerHTML = data.content_html || '<p>No content yet. Edit to add some.</p>';
        
        // **NEW**: Set content in the new editor
        editor.setMarkdown(data.content || '');

        if (data.is_folder) {
            document.body.classList.add('is-folder');
        }

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
        // **NEW**: Get content from the new editor
        const content = editor.getMarkdown();
        
        await fetch(`/api/node/${NODE_ID}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content })
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
            fileInput.value = '';
            loadNodeData();
        } else {
            alert('File upload failed.');
        }
    });

    loadNodeData();
}
