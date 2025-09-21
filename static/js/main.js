// static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    // Run the correct initialization function based on which page is loaded.
    if (document.getElementById('file-browser')) {
        initIndexPage();
    }
    if (document.querySelector('.view-container')) {
        initViewPage();
    }
});

/**
 * Logic for the main folder browsing page (index.html).
 */
function initIndexPage() {
    const fileBrowserContainer = document.getElementById('file-browser-container');
    const fileBrowser = document.getElementById('file-browser');
    const searchInput = document.getElementById('search-input');
    const searchResultsContainer = document.getElementById('search-results');
    const contextMenu = document.getElementById('context-menu');
    let searchDebounceTimer;
    let selectedItemId = null;

    // --- Event Listeners for Navigation ---
    fileBrowser.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('dblclick', () => {
            const isFolder = item.dataset.isFolder === 'true';
            const id = item.dataset.id;
            const name = item.dataset.name;

            if (isFolder) {
                const newPath = CURRENT_PATH ? `${CURRENT_PATH}/${encodeURIComponent(name)}` : encodeURIComponent(name);
                window.location.href = `/browse/${newPath}`;
            } else {
                window.location.href = `/view/${id}`;
            }
        });
    });

    // --- Context Menu Logic ---
    function showContextMenu(e) {
        e.preventDefault();
        const targetItem = e.target.closest('.file-item');
        
        contextMenu.style.display = 'none';

        if (targetItem) {
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
            targetItem.classList.add('selected');
            selectedItemId = targetItem.dataset.id;
        } else {
            selectedItemId = null;
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
        }
        
        contextMenu.style.display = 'block';
        contextMenu.style.left = `${e.pageX}px`;
        contextMenu.style.top = `${e.pageY}px`;
        
        const hasSelection = !!selectedItemId;
        document.getElementById('context-open').style.display = hasSelection ? '' : 'none';
        document.getElementById('context-rename').style.display = hasSelection ? '' : 'none';
        document.getElementById('context-delete').style.display = hasSelection ? '' : 'none';
    }
    
    fileBrowserContainer.addEventListener('contextmenu', showContextMenu);
    document.addEventListener('click', (e) => {
        if (!contextMenu.contains(e.target)) {
            contextMenu.style.display = 'none';
        }
        if (!searchResultsContainer.contains(e.target) && e.target !== searchInput) {
            searchResultsContainer.style.display = 'none';
        }
    });
    
    async function createNewItem(isFolder, isAttached = false) {
        const type = isAttached ? 'attached folder' : (isFolder ? 'folder' : 'knowledge');
        const name = prompt(`Enter name for new ${type}:`);
        if (name) {
            const response = await fetch('/api/node', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    name: name, 
                    parent_id: CURRENT_NODE_ID, 
                    is_folder: isFolder, 
                    is_attached: isAttached 
                })
            });

            if (response.ok) {
                const result = await response.json();
                // THE FIX: If a file was created, go directly to its editor page.
                if (!isFolder) {
                    window.location.href = `/view/${result.id}`;
                } else {
                    window.location.reload(); // Otherwise, just refresh the current folder.
                }
            } else {
                const error = await response.json();
                alert(`Error: ${error.error}`);
            }
        }
    }

    async function renameItem() {
        if (!selectedItemId) return;
        const currentName = document.querySelector(`.file-item[data-id="${selectedItemId}"]`).dataset.name;
        const newName = prompt("Enter new name:", currentName);
        if (newName && newName !== currentName) {
            await fetch(`/api/node/${selectedItemId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
            window.location.reload();
        }
    }

    async function deleteItem() {
        if (!selectedItemId) return;
        if (confirm("Are you sure you want to delete this item and all its contents?")) {
            await fetch(`/api/node/${selectedItemId}`, { method: 'DELETE' });
            window.location.reload();
        }
    }
    
    document.getElementById('context-new-folder').addEventListener('click', () => createNewItem(true, false));
    document.getElementById('context-new-attached').addEventListener('click', () => createNewItem(true, true));
    document.getElementById('context-new-article').addEventListener('click', () => createNewItem(false, false));
    document.getElementById('context-rename').addEventListener('click', renameItem);
    document.getElementById('context-delete').addEventListener('click', deleteItem);
    document.getElementById('context-open').addEventListener('click', () => {
        if (selectedItemId) {
            const itemElement = document.querySelector(`.file-item[data-id="${selectedItemId}"]`);
            itemElement.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        }
    });

    // --- Search Logic ---
    async function performSearch(query) {
        // ... (This function remains unchanged)
    }

    searchInput.addEventListener('input', () => {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            performSearch(searchInput.value.trim());
        }, 300);
    });
}


/**
 * Logic for the knowledge article view page (view.html).
 */
function initViewPage() {
    const nodeNameEl = document.getElementById('node-name');
    const contentDisplayEl = document.getElementById('content-display');
    const editorContainerEl = document.getElementById('editor-container');
    const saveBtn = document.getElementById('save-btn');
    const exportBtn = document.getElementById('export-context-btn');
    const uploadBtn = document.getElementById('upload-btn');
    const fileListEl = document.getElementById('file-list');

    async function loadNodeData() {
        const response = await fetch(`/api/node/${NODE_ID}`);
        if (!response.ok) {
            document.body.innerHTML = `<h1>Error: Not Found</h1><p>The requested item could not be found.</p><a href="/">Go to KnowledgeTree Home</a>`;
            return;
        }
        const data = await response.json();
        
        nodeNameEl.textContent = data.name;
        document.title = data.name;
        contentDisplayEl.innerHTML = data.content_html || '<p>No content yet. Edit to add some.</p>';

        if (data.read_only) {
            editorContainerEl.style.display = 'none';
        } else {
            const editor = new toastui.Editor({
                el: document.querySelector('#editor'),
                height: '600px',
                initialEditType: 'wysiwyg',
                previewStyle: 'tab',
                usageStatistics: false,
                initialValue: data.content || ''
            });

            saveBtn.addEventListener('click', async () => {
                await fetch(`/api/node/${NODE_ID}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: editor.getMarkdown() })
                });
                alert('Content saved!');
                const updatedData = await (await fetch(`/api/node/${NODE_ID}`)).json();
                contentDisplayEl.innerHTML = updatedData.content_html;
            });
        }
    }
    loadNodeData();
}
