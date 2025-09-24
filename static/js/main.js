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

    function showContextMenu(e) {
        e.preventDefault();
        const targetItem = e.target.closest('.file-item');

        if (!contextMenu) return;
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
        const openEl = document.getElementById('context-open');
        const renameEl = document.getElementById('context-rename');
        const deleteEl = document.getElementById('context-delete');

        if (openEl) openEl.classList.toggle('hidden', !hasSelection);
        if (renameEl) renameEl.classList.toggle('hidden', !hasSelection);
        if (deleteEl) deleteEl.classList.toggle('hidden', !hasSelection);
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
                body: JSON.stringify({ name, parent_id: CURRENT_NODE_ID, is_folder: isFolder, is_attached: isAttached })
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

    async function performSearch(query) {
        if (!query || query.length < 2) {
            if (searchResultsContainer) searchResultsContainer.style.display = 'none';
            return;
        }

        try {
            const startNodeId = searchInput.dataset.startNode;
            const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&start_node_id=${startNodeId}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
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
        } catch (error) {
            console.error("Search failed:", error);
            if(searchResultsContainer) {
                searchResultsContainer.innerHTML = '<div class="search-item">Error during search.</div>';
                searchResultsContainer.style.display = 'block';
            }
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
    const nodeNameEl = document.getElementById('node-name');
    const contentDisplayEl = document.getElementById('content-display');
    const editorContainerEl = document.getElementById('editor-container');
    const saveBtn = document.getElementById('save-btn');
    const exportBtn = document.getElementById('export-context-btn');
    const uploadBtn = document.getElementById('upload-btn');
    const fileListEl = document.getElementById('file-list');
    const fileInput = document.getElementById('file-upload-input');

    async function loadNodeData() {
        try {
            const response = await fetch(`/api/node/${NODE_ID}`);
            if (!response.ok) {
                document.body.innerHTML = `<h1>Error: Not Found</h1><p>The requested item could not be found.</p><a href="/">Go to KnowledgeTree Home</a>`;
                return;
            }
            const data = await response.json();

            if (nodeNameEl) nodeNameEl.textContent = data.name;
            document.title = data.name;
            if (contentDisplayEl) contentDisplayEl.innerHTML = data.content_html || '<p>No content yet. Edit to add some.</p>';

            if (fileListEl) {
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

            if (editorContainerEl) {
                if (data.read_only) {
                    editorContainerEl.style.display = 'none';
                } else {
                    editorContainerEl.style.display = 'block';
                    const editor = new toastui.Editor({
                        el: document.querySelector('#editor'),
                        height: '600px',
                        initialEditType: 'wysiwyg',
                        previewStyle: 'tab',
                        usageStatistics: false,
                        initialValue: data.content || ''
                    });

                    if (saveBtn) {
                        saveBtn.addEventListener('click', async () => {
                            await fetch(`/api/node/${NODE_ID}`, {
                                method: 'PUT',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ content: editor.getMarkdown() })
                            });
                            alert('Content saved!');
                            const updatedData = await (await fetch(`/api/node/${NODE_ID}`)).json();
                            if (contentDisplayEl) contentDisplayEl.innerHTML = updatedData.content_html;
                        });
                    }
                }
            }
        } catch (error) {
            console.error("Failed to load node data:", error);
            if (nodeNameEl) nodeNameEl.textContent = "Error loading content.";
        }
    }

    function buildAttachedFolderList(folders, container) {
        if (folders.length === 0) {
            container.innerHTML = '<p>No attached folders in this context.</p>';
            return;
        }

        const ul = document.createElement('ul');
        folders.forEach(folder => {
            const li = document.createElement('li');
            li.className = 'context-tree-item';

            const label = document.createElement('label');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = true; // Default to included
            checkbox.dataset.id = folder.id;

            label.innerHTML = `<i class="fas fa-paperclip"></i> ${folder.name}`;
            label.prepend(checkbox);
            li.appendChild(label);
            ul.appendChild(li);
        });
        container.appendChild(ul);
    }

    if (exportBtn) {
        exportBtn.addEventListener('click', async () => {
            const contextModal = document.getElementById('context-modal');
            const treeContainer = document.getElementById('context-tree-container');
            const contextTextarea = document.getElementById('context-textarea');
            const generateBtn = document.getElementById('generate-context-btn');

            treeContainer.innerHTML = 'Loading...';
            contextTextarea.style.display = 'none';
            treeContainer.style.display = 'block';
            generateBtn.style.display = 'block';
            contextModal.style.display = 'block';

            const response = await fetch(`/api/context/tree/${NODE_ID}`);
            const data = await response.json();

            treeContainer.innerHTML = ''; // Clear loading message
            buildAttachedFolderList(data.attached_folders, treeContainer);
        });
    }

    const generateContextBtn = document.getElementById('generate-context-btn');
    if (generateContextBtn) {
        generateContextBtn.addEventListener('click', async () => {
            const treeContainer = document.getElementById('context-tree-container');
            const contextTextarea = document.getElementById('context-textarea');
            const modalMessage = document.getElementById('modal-message');

            const excludedIds = Array.from(treeContainer.querySelectorAll('input[type="checkbox"]:not(:checked)'))
                                     .map(cb => cb.dataset.id);

            const response = await fetch(`/api/context/${NODE_ID}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ excluded_ids: excludedIds })
            });
            const data = await response.json();

            treeContainer.style.display = 'none';
            generateContextBtn.style.display = 'none';
            contextTextarea.style.display = 'block';

            contextTextarea.value = data.context;
            contextTextarea.focus();
            contextTextarea.select();

            modalMessage.textContent = 'Auto-copied to clipboard! You can also copy the text below.';

            if (navigator.clipboard) {
                try {
                    await navigator.clipboard.writeText(data.context);
                } catch (err) {
                    console.error('Failed to auto-copy to clipboard:', err);
                    modalMessage.textContent = 'Could not auto-copy. Please copy the text manually.';
                }
            }
        });
    }


    // --- Modal Closing Logic ---
    const closeModalBtn = document.getElementById('close-modal-btn');
    const contextModal = document.getElementById('context-modal');
    if (closeModalBtn && contextModal) {
        closeModalBtn.addEventListener('click', () => {
            contextModal.style.display = 'none';
        });
        window.addEventListener('click', (event) => {
            if (event.target == contextModal) {
                contextModal.style.display = 'none';
            }
        });
    }

    if (uploadBtn) {
        uploadBtn.addEventListener('click', async () => {
            if (!fileInput || fileInput.files.length === 0) {
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
    }

    loadNodeData();
}
