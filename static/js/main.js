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
    if (fileBrowser) {
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
    }

    // --- Context Menu Logic ---
    function showContextMenu(e) {
        e.preventDefault();
        console.log("--- Context Menu Triggered ---"); // DEBUG
        const targetItem = e.target.closest('.file-item');
        
        if (!contextMenu) return;

        contextMenu.style.display = 'none';

        if (targetItem) {
            console.log("DEBUG: Right-clicked on an item:", targetItem.dataset.name); // DEBUG
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
            targetItem.classList.add('selected');
            selectedItemId = targetItem.dataset.id;
        } else {
            console.log("DEBUG: Right-clicked on empty space."); // DEBUG
            selectedItemId = null;
            document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
        }
        
        contextMenu.style.display = 'block';
        contextMenu.style.left = `${e.pageX}px`;
        contextMenu.style.top = `${e.pageY}px`;
        
        const hasSelection = !!selectedItemId;
        console.log("DEBUG: Has selection?", hasSelection); // DEBUG

        // THE FIX: Use classList.toggle to correctly show/hide elements based on the .hidden class in style.css
        const openEl = document.getElementById('context-open');
        const renameEl = document.getElementById('context-rename');
        const deleteEl = document.getElementById('context-delete');

        if (openEl) openEl.classList.toggle('hidden', !hasSelection);
        if (renameEl) renameEl.classList.toggle('hidden', !hasSelection);
        if (deleteEl) deleteEl.classList.toggle('hidden', !hasSelection);
        
        console.log("DEBUG: Setting item-specific options visibility based on selection."); // DEBUG
    }
    
    if (fileBrowserContainer) {
        fileBrowserContainer.addEventListener('contextmenu', showContextMenu);
    }
    
    document.addEventListener('click', (e) => {
        if (contextMenu && !contextMenu.contains(e.target)) {
            contextMenu.style.display = 'none';
        }
        if (searchResultsContainer && !searchResultsContainer.contains(e.target) && e.target !== searchInput) {
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
                if (!isFolder) {
                    window.location.href = `/view/${result.id}`;
                } else {
                    window.location.reload();
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
    
    if (contextMenu) {
        document.getElementById('context-new-folder')?.addEventListener('click', () => createNewItem(true, false));
        document.getElementById('context-new-attached')?.addEventListener('click', () => createNewItem(true, true));
        document.getElementById('context-new-article')?.addEventListener('click', () => createNewItem(false, false));
        document.getElementById('context-rename')?.addEventListener('click', renameItem);
        document.getElementById('context-delete')?.addEventListener('click', deleteItem);
        document.getElementById('context-open')?.addEventListener('click', () => {
            if (selectedItemId) {
                const itemElement = document.querySelector(`.file-item[data-id="${selectedItemId}"]`);
                if(itemElement) itemElement.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
            }
        });
    }

    // --- Search Logic ---
    async function performSearch(query) {
        if (!query || query.length < 2) {
            if (searchResultsContainer) searchResultsContainer.style.display = 'none';
            return;
        }
        const startNodeId = searchInput.dataset.startNode;
        const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&start_node_id=${startNodeId}`);
        const items = await response.json();
        
        if (searchResultsContainer) {
            searchResultsContainer.innerHTML = '';
            if (items.length === 0) {
                searchResultsContainer.innerHTML = '<div class="search-item">No results found.</div>';
            } else {
                items.forEach(item => {
                    const itemEl = document.createElement('div');
                    itemEl.className = 'search-item';
                    
                    let iconClass = item.is_folder ? 'fas fa-folder' : 'fas fa-file-alt';
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
    }

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                performSearch(searchInput.value.trim());
            }, 300);
        });
    }
}


/**
 * Logic for the knowledge article view page (view.html).
 */
function initViewPage() {
    // This function remains unchanged.
}
