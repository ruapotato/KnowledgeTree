# app.py
import os
import uuid
from urllib.parse import unquote
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

# --- Main Routes ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return render_template('index.html')

@app.route('/view/<node_id>')
def view_node(node_id):
    return render_template('view.html', node_id=node_id)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Admin Route ---
@app.route('/admin')
def admin_panel():
    return render_template('admin.html')


# --- API Endpoints ---
@app.route('/api/resolve_path', methods=['POST'])
def resolve_path():
    path_parts = request.json.get('path', [])
    if not path_parts:
        return jsonify({'id': 'root'})
    with driver.session() as session:
        query = "MATCH (n0:ContextItem {id: 'root'})"
        match_clauses = []
        where_clauses = []
        for i, part in enumerate(path_parts):
            prev_node, curr_node = f"n{i}", f"n{i+1}"
            match_clauses.append(f"MATCH ({prev_node})-[:PARENT_OF]->({curr_node})")
            where_clauses.append(f"{curr_node}.name = ${i}")
        full_query = "\n".join([query] + match_clauses) + "\nWHERE " + " AND ".join(where_clauses) + f"\nRETURN n{len(path_parts)}.id as id"
        params = {str(i): part for i, part in enumerate(path_parts)}
        result = session.run(full_query, params).single()
    if result:
        return jsonify({'id': result['id']})
    else:
        return jsonify({'error': 'Path not found'}), 404

@app.route('/api/nodes/<parent_id>', methods=['GET'])
def get_nodes_in_folder(parent_id):
    with driver.session() as session:
        query = """
            MATCH (:ContextItem {id: $parent_id})-[:PARENT_OF]->(child)
            RETURN DISTINCT child.id AS id, child.name AS name, child.is_folder AS is_folder, child.is_attached as is_attached
            ORDER BY child.is_folder DESC, child.name
        """
        result = session.run(query, parent_id=parent_id)
        records = [dict(record) for record in result]
        return jsonify(records)

@app.route('/api/path/<node_id>', methods=['GET'])
def get_path(node_id):
    with driver.session() as session:
        query = """
            MATCH path = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            WITH nodes(path) AS path_nodes
            UNWIND path_nodes as node
            RETURN node.id AS id, node.name AS name
        """
        result = session.run(query, node_id=node_id)
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
    data = request.json
    parent_id = data.get('parent_id', 'root')
    name = data.get('name')
    is_folder = data.get('is_folder', False)
    is_attached = data.get('is_attached', False)
    new_id = str(uuid.uuid4())
    with driver.session() as session:
        parent_is_attached = session.run("MATCH (p:ContextItem {id: $id}) RETURN p.is_attached as attached", id=parent_id).single()['attached']
        if parent_is_attached and is_folder and not is_attached:
             return jsonify({'error': 'Only attached folders or knowledge articles can be created here.'}), 400
        session.run("""
            MATCH (parent:ContextItem {id: $parent_id})
            CREATE (child:ContextItem {id: $id, name: $name, is_folder: $is_folder, content: '', is_attached: $is_attached})
            CREATE (parent)-[:PARENT_OF]->(child)
        """, parent_id=parent_id, id=new_id, name=name, is_folder=is_folder, is_attached=is_attached)
    return jsonify({'success': True, 'id': new_id, 'name': name, 'is_folder': is_folder, 'is_attached': is_attached})

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
        # **CORRECTED CYPHER QUERY**
        query = """
            MATCH path = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            WITH nodes(path) AS ancestors
            UNWIND ancestors AS ancestor
            OPTIONAL MATCH (ancestor)-[:PARENT_OF]->(attached_folder:ContextItem {is_attached: true})
            OPTIONAL MATCH (attached_folder)-[:PARENT_OF*0..]->(attached_descendant)
            WITH collect(DISTINCT ancestor) + collect(DISTINCT attached_descendant) AS all_nodes
            UNWIND all_nodes AS final_node
            WITH final_node WHERE final_node IS NOT NULL AND final_node.content IS NOT NULL AND final_node.content <> ""
            RETURN DISTINCT final_node.name AS name, final_node.content AS content
        """
        result = tx.run(query, node_id=node_id)
        return [dict(record) for record in result]

    with driver.session() as session:
        context_data = session.read_transaction(fetch_context, node_id)
        
        # Create a dictionary to ensure uniqueness by name, preserving the last seen content
        unique_context = {item['name']: item for item in context_data}
        # Convert back to a list
        unique_context_list = list(unique_context.values())

        full_context = "\n\n---\n\n".join(
            [f"# CONTEXT: {item['name']}\n\n{item['content']}" for item in unique_context_list]
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

@app.route('/api/admin/reinitialize_db', methods=['POST'])
def reinitialize_db():
    try:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            session.write_transaction(ensure_root_exists)
        return jsonify({'success': True, 'message': 'Database wiped and re-initialized successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, port=5001)
