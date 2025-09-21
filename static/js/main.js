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
    let selectedItemType = { is_folder: false };

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

    // --- Context Menu Logic (Restored and Fixed) ---
    function showContextMenu(e) {
        e.preventDefault();
        const targetItem = e.target.closest('.file-item');
        
        contextMenu.style.display = 'none'; // Hide first

        if (targetItem) {
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
            targetItem.classList.add('selected');
            selectedItemId = targetItem.dataset.id;
            selectedItemType.is_folder = targetItem.dataset.isFolder === 'true';
        } else {
            selectedItemId = null;
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
        }
        
        // Position and show the menu
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
                body: JSON.stringify({ name, parent_id: CURRENT_NODE_ID, is_folder: isFolder, is_attached: isAttached })
            });
            if (response.ok) {
                window.location.reload();
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
        if (!query || query.length < 2) {
            searchResultsContainer.style.display = 'none';
            return;
        }
        const startNodeId = searchInput.dataset.startNode;
        const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&start_node_id=${startNodeId}`);
        const items = await response.json();
        
        searchResultsContainer.innerHTML = '';
        if (items.length === 0) {
            searchResultsContainer.innerHTML = '<div class="search-item">No results found.</div>';
        } else {
            items.forEach(item => {
                const itemEl = document.createElement('div');
                itemEl.className = 'search-item';
                
                let iconClass = item.is_folder ? 'fas fa-folder' : 'fas fa-file-alt';
                // THE FIX: The path from the API now includes the item's own name, so we use it directly.
                let pathParts = item.folder_path.split('/').map(p => decodeURIComponent(p));
                let itemName = pathParts.pop() || '';
                let parentPath = pathParts.join(' / ');
                
                if (parentPath.length > 40) {
                    parentPath = `...${parentPath.substring(parentPath.length - 37)}`;
                }

                itemEl.innerHTML = `
                    <div>
                        <span class="search-item-name"><i class="${iconClass}"></i> ${itemName}</span>
                        <div class="search-item-path">${parentPath}</div>
                    </div>
                `;
                
                itemEl.addEventListener('click', () => {
                    // Navigate to the correct server-rendered URL.
                    if (item.is_folder) {
                        window.location.href = `/browse/${item.folder_path}`;
                    } else {
                        window.location.href = `/view/${item.id}`;
                    }
                });
                searchResultsContainer.appendChild(itemEl);
            });
        }
        searchResultsContainer.style.display = 'block';
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
    // This function remains unchanged.
}
