# app.py
import os
import uuid
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_from_directory
from neo4j import GraphDatabase, basic_auth
import markdown

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- Neo4j Connection ---
uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))

# Helper to ensure the root node exists
def ensure_root_exists(tx):
    tx.run("""
        MERGE (r:ContextItem {id: 'root', name: 'KnowledgeTree Root'})
        ON CREATE SET r.content = '# Welcome to KnowledgeTree', r.is_folder = true
    """)

with driver.session() as session:
    session.write_transaction(ensure_root_exists)

# --- Main Routes ---
@app.route('/')
def index():
    """Renders the main file manager interface."""
    return render_template('index.html')

@app.route('/view/<node_id>')
def view_node(node_id):
    """Renders the view/edit page for a single node."""
    return render_template('view.html', node_id=node_id)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serves uploaded files."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- API Endpoints ---
@app.route('/api/nodes/<parent_id>', methods=['GET'])
def get_nodes_in_folder(parent_id):
    """Fetches the immediate children of a given parent node."""
    with driver.session() as session:
        result = session.run("""
            MATCH (:ContextItem {id: $parent_id})-[:PARENT_OF]->(child:ContextItem)
            RETURN child.id AS id, child.name AS name, child.is_folder AS is_folder
            ORDER BY child.is_folder DESC, child.name
        """, parent_id=parent_id)
        return jsonify([dict(record) for record in result])

@app.route('/api/path/<node_id>', methods=['GET'])
def get_path(node_id):
    """Gets the full path (breadcrumbs) to a node."""
    if node_id == 'root':
         with driver.session() as session:
            root_node = session.run("MATCH (n:ContextItem {id: 'root'}) RETURN n.id as id, n.name as name").single()
            return jsonify([dict(root_node)])

    with driver.session() as session:
        result = session.run("""
            MATCH path = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            WITH nodes(path) AS path_nodes
            UNWIND path_nodes as node
            RETURN node.id AS id, node.name AS name
        """, node_id=node_id)
        return jsonify([dict(record) for record in result])


@app.route('/api/node/<node_id>', methods=['GET'])
def get_node(node_id):
    """Fetches data for a single node."""
    def fetch_node(tx, node_id):
        query = """
        MATCH (n:ContextItem {id: $node_id})
        OPTIONAL MATCH (n)-[:HAS_FILE]->(f:File)
        RETURN n.id AS id, n.name AS name, n.content AS content, n.is_folder AS is_folder,
               collect({id: f.id, filename: f.filename}) AS files
        """
        result = tx.run(query, node_id=node_id).single()
        if result:
            data = dict(result)
            data['content_html'] = markdown.markdown(data.get('content', ''), extensions=['fenced_code', 'tables'])
            data['files'] = [file for file in data.get('files', []) if file and file.get('id')]
            return data
        return None

    with driver.session() as session:
        node_data = session.read_transaction(fetch_node, node_id)
        return jsonify(node_data if node_data else {})

@app.route('/api/node', methods=['POST'])
def create_node():
    """Creates a new node (article or folder)."""
    data = request.json
    parent_id = data.get('parent_id', 'root')
    name = data.get('name')
    is_folder = data.get('is_folder', False)
    new_id = str(uuid.uuid4())

    with driver.session() as session:
        session.run("""
            MATCH (parent:ContextItem {id: $parent_id})
            CREATE (child:ContextItem {id: $id, name: $name, is_folder: $is_folder, content: ''})
            CREATE (parent)-[:PARENT_OF]->(child)
        """, parent_id=parent_id, id=new_id, name=name, is_folder=is_folder)
    return jsonify({'success': True, 'id': new_id, 'name': name, 'is_folder': is_folder})

@app.route('/api/node/<node_id>', methods=['PUT'])
def update_node(node_id):
    """Updates a node's content or name."""
    data = request.json
    with driver.session() as session:
        if 'content' in data:
            session.run("MATCH (n:ContextItem {id: $id}) SET n.content = $content", id=node_id, content=data['content'])
        if 'name' in data:
            session.run("MATCH (n:ContextItem {id: $id}) SET n.name = $name", id=node_id, name=data['name'])
    return jsonify({'success': True})

@app.route('/api/node/<node_id>', methods=['DELETE'])
def delete_node(node_id):
    """Deletes a node and all its children."""
    with driver.session() as session:
        # This query finds the node, finds all children recursively, and deletes them all.
        session.run("""
            MATCH (n:ContextItem {id: $node_id})
            OPTIONAL MATCH (n)-[:PARENT_OF*0..]->(child)
            DETACH DELETE n, child
        """, id=node_id)
    return jsonify({'success': True})


@app.route('/api/context/<node_id>', methods=['GET'])
def get_context(node_id):
    """Fetches the full inherited context for a node."""
    def fetch_context(tx, node_id):
        query = """
        MATCH (start_node:ContextItem {id: $node_id})
        MATCH path = (root:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(start_node)
        WITH nodes(path) AS context_nodes
        UNWIND context_nodes AS node
        RETURN DISTINCT node.name AS name, node.content AS content
        """
        result = tx.run(query, node_id=node_id)
        return [dict(record) for record in result]

    with driver.session() as session:
        context_data = session.read_transaction(fetch_context, node_id)
        full_context = "\n\n---\n\n".join(
            [f"# CONTEXT: {item['name']}\n\n{item['content']}" for item in context_data if item['content']]
        )
        return jsonify({'context': full_context})

@app.route('/api/upload/<node_id>', methods=['POST'])
def upload_file_to_node(node_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file:
        filename = file.filename
        file_id = str(uuid.uuid4())
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        with driver.session() as session:
            session.run("""
                MATCH (n:ContextItem {id: $node_id})
                CREATE (f:File {id: $file_id, filename: $filename})
                CREATE (n)-[:HAS_FILE]->(f)
            """, node_id=node_id, file_id=file_id, filename=filename)
        return jsonify({'success': True, 'filename': filename})
    return jsonify({'error': 'File upload failed'}), 500

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, port=5001)
