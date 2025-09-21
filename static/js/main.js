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
    const fileBrowser = document.getElementById('file-browser');
    const searchInput = document.getElementById('search-input');
    const searchResultsContainer = document.getElementById('search-results');
    let searchDebounceTimer;

    // Add navigation handlers for all file and folder items.
    fileBrowser.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('dblclick', () => {
            const isFolder = item.dataset.isFolder === 'true';
            const id = item.dataset.id;
            const name = item.dataset.name;

            if (isFolder) {
                // Construct the new URL by appending the folder name to the current path.
                const newPath = CURRENT_PATH ? `${CURRENT_PATH}/${encodeURIComponent(name)}` : encodeURIComponent(name);
                window.location.href = `/browse/${newPath}`;
            } else {
                // Navigate directly to the view page for files.
                window.location.href = `/view/${id}`;
            }
        });
    });

    /**
     * Fetches and displays live search results as the user types.
     */
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
                let pathParts = item.folder_path.split('/');
                let itemName = decodeURIComponent(pathParts.pop() || '');
                let parentPath = pathParts.map(p => decodeURIComponent(p)).join(' / ');
                
                if (parentPath.length > 40) { // Truncate long paths
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

    // Add debounced input listener for live search.
    searchInput.addEventListener('input', () => {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            performSearch(searchInput.value.trim());
        }, 300);
    });
    
    // Hide search results when clicking anywhere else on the page.
    document.addEventListener('click', (e) => {
        if (!searchResultsContainer.contains(e.target) && e.target !== searchInput) {
            searchResultsContainer.style.display = 'none';
        }
    });
}

/**
 * Logic for the knowledge article view page (view.html).
 */
function initViewPage() {
    const nodeNameEl = document.getElementById('node-name');
    const contentDisplayEl = document.getElementById('content-display');
    const editorContainerEl = document.getElementById('editor-container');
    
    // This function fetches and renders the content for the current article.
    async function loadNodeData() {
        const response = await fetch(`/api/node/${NODE_ID}`);
        if (!response.ok) {
            document.body.innerHTML = `<h1>Error: Not Found</h1><p>The requested item could not be found.</p><a href="/">Go to KnowledgeTree Home</a>`;
            return;
        }
        const data = await response.json();
        
        nodeNameEl.textContent = data.name;
        document.title = data.name;
        contentDisplayEl.innerHTML = data.content_html || '<p>No content yet.</p>';

        if (data.read_only) {
            editorContainerEl.style.display = 'none';
        } else {
            // Initialize the editor only if the file is not read-only.
            const editor = new toastui.Editor({
                el: document.querySelector('#editor'),
                height: '600px',
                initialEditType: 'wysiwyg',
                previewStyle: 'tab',
                usageStatistics: false,
                initialValue: data.content || ''
            });

            document.getElementById('save-btn').addEventListener('click', async () => {
                await fetch(`/api/node/${NODE_ID}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: editor.getMarkdown() })
                });
                alert('Content saved!');
                // Reload content display after saving
                const updatedData = await (await fetch(`/api/node/${NODE_ID}`)).json();
                contentDisplayEl.innerHTML = updatedData.content_html;
            });
        }
    }
    loadNodeData();
}
