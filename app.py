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
        ON CREATE SET r.content = '# Welcome to KnowledgeTree', r.is_folder = true, r.is_attached = false
    """)

with driver.session() as session:
    session.write_transaction(ensure_root_exists)

# --- Main Routes (Unchanged) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/view/<node_id>')
def view_node(node_id):
    return render_template('view.html', node_id=node_id)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- API Endpoints ---
@app.route('/api/nodes/<parent_id>', methods=['GET'])
def get_nodes_in_folder(parent_id):
    """
    Fetches items for the file browser.
    - Fixes the double-render bug by using DISTINCT.
    - Implements "paperclip" logic by including items from attached sub-folders.
    """
    with driver.session() as session:
        # This query gets all direct children, AND all children of "attached" folders one level deep.
        query = """
            // Get all direct children
            MATCH (:ContextItem {id: $parent_id})-[:PARENT_OF]->(child)
            RETURN DISTINCT child.id AS id, child.name AS name, child.is_folder AS is_folder, child.is_attached as is_attached
            UNION
            // Also get the children from any attached folders
            MATCH (:ContextItem {id: $parent_id})-[:PARENT_OF]->(:ContextItem {is_attached: true})-[:PARENT_OF]->(grandchild)
            RETURN DISTINCT grandchild.id AS id, grandchild.name AS name, grandchild.is_folder AS is_folder, grandchild.is_attached as is_attached
        """
        result = session.run(query, parent_id=parent_id)
        
        # We need to sort in Python now since UNION prevents ORDER BY in the query
        records = [dict(record) for record in result]
        records.sort(key=lambda x: (not x.get('is_folder', False), x.get('name', '')))
        
        return jsonify(records)

@app.route('/api/path/<node_id>', methods=['GET'])
def get_path(node_id):
    if node_id == 'root':
         with driver.session() as session:
            root_node = session.run("MATCH (n:ContextItem {id: 'root'}) RETURN n.id as id, n.name as name").single()
            return jsonify([dict(root_node)])
    with driver.session() as session:
        result = session.run("""
            MATCH path = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            WHERE NOT any(n IN nodes(path) WHERE n.is_attached = true AND n.id <> $node_id)
            WITH nodes(path) AS path_nodes
            UNWIND path_nodes as node
            RETURN node.id AS id, node.name AS name
        """, node_id=node_id)
        return jsonify([dict(record) for record in result])

@app.route('/api/node/<node_id>', methods=['GET'])
def get_node(node_id):
    def fetch_node(tx, node_id):
        query = """
        MATCH (n:ContextItem {id: $node_id})
        OPTIONAL MATCH (n)-[:HAS_FILE]->(f:File)
        RETURN n.id AS id, n.name AS name, n.content AS content, n.is_folder AS is_folder, n.is_attached as is_attached,
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
    """Creates a new node, handling attached folder logic."""
    data = request.json
    parent_id = data.get('parent_id', 'root')
    name = data.get('name')
    is_folder = data.get('is_folder', False)
    is_attached = data.get('is_attached', False)
    new_id = str(uuid.uuid4())

    with driver.session() as session:
        # Enforce rule: only attached folders can be created in attached folders
        parent_is_attached = session.run("MATCH (p:ContextItem {id: $id}) RETURN p.is_attached as attached", id=parent_id).single()['attached']
        if parent_is_attached and not is_attached:
             return jsonify({'error': 'Only attached items can be created in an attached folder.'}), 400
        if parent_is_attached and not is_folder:
             return jsonify({'error': 'Only folders (not articles) can be created in an attached folder.'}), 400

        session.run("""
            MATCH (parent:ContextItem {id: $parent_id})
            CREATE (child:ContextItem {id: $id, name: $name, is_folder: $is_folder, content: '', is_attached: $is_attached})
            CREATE (parent)-[:PARENT_OF]->(child)
        """, parent_id=parent_id, id=new_id, name=name, is_folder=is_folder, is_attached=is_attached)
    return jsonify({'success': True, 'id': new_id, 'name': name, 'is_folder': is_folder, 'is_attached': is_attached})

# Unchanged functions: update_node, delete_node, get_context, upload_file_to_node, main execution block
# ... (include the rest of the functions from the previous app.py here)
@app.route('/api/node/<node_id>', methods=['PUT'])
def update_node(node_id):
    data = request.json
    with driver.session() as session:
        if 'content' in data:
            session.run("MATCH (n:ContextItem {id: $id}) SET n.content = $content", id=node_id, content=data['content'])
        if 'name' in data:
            session.run("MATCH (n:ContextItem {id: $id}) SET n.name = $name", id=node_id, name=data['name'])
    return jsonify({'success': True})

@app.route('/api/node/<node_id>', methods=['DELETE'])
def delete_node(node_id):
    with driver.session() as session:
        session.run("""
            MATCH (n:ContextItem {id: $node_id})
            OPTIONAL MATCH (n)-[:PARENT_OF*0..]->(child)
            DETACH DELETE n, child
        """, id=node_id)
    return jsonify({'success': True})

@app.route('/api/context/<node_id>', methods=['GET'])
def get_context(node_id):
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
