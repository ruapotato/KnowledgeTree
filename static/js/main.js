// static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    // Check which page we are on
    if (document.getElementById('file-manager')) {
        initIndexPage();
    }
    if (document.querySelector('.view-container')) {
        initViewPage();
    }
});

let selectedNodeId = 'root'; // Default to root

// --- Index Page Logic ---
function initIndexPage() {
    const fileManager = document.getElementById('file-manager');
    const newNodeNameInput = document.getElementById('new-node-name');

    function renderTree(nodes, container) {
        const ul = document.createElement('ul');
        nodes.forEach(node => {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = `/view/${node.id}`;
            a.dataset.id = node.id;
            
            const icon = document.createElement('i');
            icon.className = node.is_folder ? 'fas fa-folder' : 'fas fa-file-alt';
            a.appendChild(icon);
            a.appendChild(document.createTextNode(` ${node.name}`));

            // Click to select for adding new items
            a.addEventListener('click', (e) => {
                e.preventDefault(); // Prevent navigation
                document.querySelectorAll('#file-manager a').forEach(el => el.classList.remove('selected'));
                a.classList.add('selected');
                selectedNodeId = node.id;
                
                // On double click, navigate to view page
                if (a.dataset.clickedOnce) {
                    window.location.href = a.href;
                } else {
                    a.dataset.clickedOnce = true;
                    setTimeout(() => { a.dataset.clickedOnce = false; }, 300); // 300ms for double click
                }
            });

            li.appendChild(a);

            if (node.children && node.children.length > 0) {
                renderTree(node.children, li);
            }
            ul.appendChild(li);
        });
        container.appendChild(ul);
    }

    async function loadTree() {
        const response = await fetch('/api/tree');
        const treeData = await response.json();
        fileManager.innerHTML = '';
        renderTree(treeData, fileManager);
        // Auto-select root initially
        const rootLink = fileManager.querySelector('a[data-id="root"]');
        if (rootLink) rootLink.classList.add('selected');
    }
    
    async function createNode(isFolder) {
        const name = newNodeNameInput.value.trim();
        if (!name) {
            alert('Please enter a name.');
            return;
        }
        await fetch('/api/node', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, parent_id: selectedNodeId, is_folder: isFolder })
        });
        newNodeNameInput.value = '';
        loadTree(); // Refresh tree
    }

    document.getElementById('add-article-btn').addEventListener('click', () => createNode(false));
    document.getElementById('add-folder-btn').addEventListener('click', () => createNode(true));
    
    loadTree();
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
