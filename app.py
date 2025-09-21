# app.py
import os
import uuid
import schedule
import time
import threading
import json
from urllib.parse import unquote, quote
from dotenv import load_dotenv, set_key
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from neo4j import GraphDatabase, basic_auth
import markdown
from scripts.pull_freshservice import sync_companies_and_users
from scripts.pull_datto import sync_datto_devices

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# --- Neo4j Connection ---
uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=basic_auth(user, password))

# --- DB Helper ---
def ensure_root_exists(tx):
    tx.run("""
        MERGE (r:ContextItem {id: 'root', name: 'KnowledgeTree Root'})
        ON CREATE SET r.content = '# Welcome to KnowledgeTree', r.is_folder = true, r.is_attached = false
    """)

with driver.session() as session:
    session.write_transaction(ensure_root_exists)

# --- URL Generation Helper ---
@app.template_filter('quote_plus')
def quote_plus_filter(s):
    # This makes the URL encoding function available in Jinja templates
    return quote(s)

# --- Main Routes ---

@app.route('/')
def index():
    # The root of the site now redirects to the main browser view.
    return redirect(url_for('browse'))

@app.route('/browse/', defaults={'path': ''})
@app.route('/browse/<path:path>')
def browse(path):
    """
    This is now the ONLY route for browsing the knowledge tree.
    It resolves the path server-side and passes all necessary data to the template.
    """
    path_parts = [p for p in path.split('/') if p]
    
    with driver.session() as session:
        # 1. Resolve path to get the current node ID
        query = "MATCH (n0:ContextItem {id: 'root'})"
        match_clauses, where_clauses, params = [], [], {}
        for i, part in enumerate(path_parts):
            prev_node, curr_node = f"n{i}", f"n{i+1}"
            param_name = f"part_{i}"
            match_clauses.append(f"MATCH ({prev_node})-[:PARENT_OF]->({curr_node})")
            where_clauses.append(f"{curr_node}.name = ${param_name}")
            params[param_name] = unquote(part)
        
        full_query = "\n".join([query] + match_clauses) + ("\nWHERE " + " AND ".join(where_clauses) if where_clauses else "") + f"\nRETURN n{len(path_parts)}.id as id"
        
        result = session.run(full_query, params).single()
        node_id = result['id'] if result else 'root'

        # 2. Get children of the current node
        children_query = """
            MATCH (:ContextItem {id: $parent_id})-[:PARENT_OF]->(child)
            RETURN DISTINCT child.id AS id, child.name AS name, child.is_folder AS is_folder, 
                   child.is_attached as is_attached, child.read_only as read_only
            ORDER BY child.is_folder DESC, child.name
        """
        children_result = session.run(children_query, parent_id=node_id)
        items = [dict(record) for record in children_result]

        # 3. Get breadcrumb path for navigation
        path_query = """
            MATCH path = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            RETURN [n in nodes(path) | n.name] AS names
        """
        path_result = session.run(path_query, node_id=node_id).single()
        breadcrumb_names = path_result['names'] if path_result else ["KnowledgeTree Root"]

    return render_template('index.html', 
                           items=items, 
                           breadcrumb_names=breadcrumb_names, 
                           current_path=path,
                           current_node_id=node_id)

@app.route('/view/<node_id>')
def view_node(node_id):
    """
    This route now reliably finds the parent's path for a correct "back" button link.
    """
    with driver.session() as session:
        # Find the parent of the current node to construct the back link
        path_query = """
            MATCH (parent:ContextItem)-[:PARENT_OF]->(:ContextItem {id: $node_id})
            WITH parent
            MATCH path = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(parent)
            RETURN [n IN nodes(path) | n.name] AS names
        """
        result = session.run(path_query, node_id=node_id).single()
        
        parent_path = ''
        if result and result['names']:
            # Create a URL-safe path from the names list, skipping the root
            parent_path = "/".join([quote(name) for name in result['names'][1:]])

    return render_template('view.html', node_id=node_id, parent_path=parent_path)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Admin Routes ---
@app.route('/admin')
def admin_panel():
    # A simple admin page placeholder
    return render_template('admin.html')

# --- API Endpoints ---

@app.route('/api/search', methods=['GET'])
def search_nodes():
    query = request.args.get('query', '')
    start_node_id = request.args.get('start_node_id', 'root')

    if not query: return jsonify([])

    with driver.session() as session:
        # THE FIX: This query now finds the full path from the absolute root
        # for every search result, ensuring correct URLs.
        result = session.run("""
            MATCH (startNode:ContextItem {id: $start_node_id})-[:PARENT_OF*0..]->(node)
            WHERE toLower(node.name) CONTAINS toLower($query) OR toLower(node.content) CONTAINS toLower($query)
            WITH DISTINCT node
            MATCH p = (:ContextItem {id: 'root'})-[:PARENT_OF*..]->(node)
            RETURN node.id as id,
                   node.name as name,
                   node.is_folder as is_folder,
                   [n IN nodes(p) | n.name] AS path_names
            LIMIT 15
            """, {'start_node_id': start_node_id, 'query': query})
        
        processed_results = []
        for record in result:
            record_dict = dict(record)
            path_list = record_dict['path_names'][1:] # Exclude root
            folder_path = "/".join([quote(name) for name in path_list])
            record_dict['folder_path'] = folder_path
            processed_results.append(record_dict)

        return jsonify(processed_results)

@app.route('/api/node/<node_id>', methods=['GET'])
def get_node(node_id):
    def fetch_node(tx, node_id):
        # Using OPTIONAL MATCH to gracefully handle nodes that might not have files
        query = """
        MATCH (n:ContextItem {id: $node_id})
        OPTIONAL MATCH (n)-[:HAS_FILE]->(f:File)
        RETURN n.id AS id, n.name AS name, n.content AS content, n.is_folder AS is_folder, 
               n.is_attached as is_attached, n.read_only as read_only,
               collect({id: f.id, filename: f.filename}) AS files
        """
        result = tx.run(query, node_id=node_id).single()
        if result:
            data = dict(result)
            content = data.get('content') or ''
            data['content_html'] = markdown.markdown(content, extensions=['fenced_code', 'tables'])
            # Ensure files list is clean even if there are no attachments
            data['files'] = [f for f in data.get('files', []) if f['id'] is not None]
            return data
        return None
    
    with driver.session() as session:
        node_data = session.read_transaction(fetch_node, node_id)
        if node_data:
            return jsonify(node_data)
        else:
            return jsonify({'error': 'Node not found'}), 404

@app.route('/api/node/<node_id>', methods=['PUT'])
def update_node(node_id):
    data = request.json
    with driver.session() as session:
        if 'content' in data:
            session.run("MATCH (n:ContextItem {id: $id}) SET n.content = $content", 
                        id=node_id, content=data['content'])
        if 'name' in data:
            session.run("MATCH (n:ContextItem {id: $id}) SET n.name = $name", 
                        id=node_id, name=data['name'])
    return jsonify({'success': True})

@app.route('/api/node/<node_id>', methods=['DELETE'])
def delete_node(node_id):
    with driver.session() as session:
        session.run("""
            MATCH (n:ContextItem {id: $id})
            OPTIONAL MATCH (n)-[:PARENT_OF*0..]->(child)
            DETACH DELETE n, child
        """, id=node_id)
    return jsonify({'success': True})

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
        return jsonify({'success': True, 'message': 'Database wiped and re-initialized.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/save_settings', methods=['POST'])
def save_settings():
    settings = request.json
    for key, value in settings.items():
        set_key('.env', key, value)
    return jsonify({'success': True, 'message': 'Settings saved.'})

@app.route('/api/admin/run_job/<job_name>', methods=['POST'])
def run_job(job_name):
    if job_name == 'freshservice':
        threading.Thread(target=sync_companies_and_users).start()
        return jsonify({'success': True, 'message': 'Freshservice sync started.'})
    elif job_name == 'datto':
        threading.Thread(target=sync_datto_devices).start()
        return jsonify({'success': True, 'message': 'Datto sync started.'})
    return jsonify({'success': False, 'error': 'Invalid job name.'}), 400

@app.route('/api/admin/export', methods=['GET'])
def export_user_data():
    try:
        export_file_path = "export.json"
        with driver.session() as session:
            result = session.run(f"""
                CALL apoc.export.json.query(
                    'MATCH (n) WHERE n.read_only IS NULL OR n.read_only = false
                     OPTIONAL MATCH (n)-[r]->(m) WHERE m.read_only IS NULL OR m.read_only = false
                     RETURN n, r, m',
                    "{export_file_path}", {{stream: true, writeNodeProperties: true}})
                YIELD file
                RETURN file
            """).single()
            if result and result['file']:
                return send_file(export_file_path, as_attachment=True, download_name='knowledgetree_export.json')
            else:
                 return jsonify({'success': False, 'error': 'Export failed or produced no data.'}), 500
    except Exception as e:
        if "Failed to invoke procedure `apoc.export.json.query`" in str(e):
             return jsonify({'success': False, 'error': 'APOC extension not installed on Neo4j server.'}), 500
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/import', methods=['POST'])
def import_user_data():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file:
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'import_data.json')
            file.save(file_path)
            with driver.session() as session:
                session.run(f"""
                    CALL apoc.import.json("file://{os.path.abspath(file_path)}")
                """)
            os.remove(file_path)
            return jsonify({'success': True})
        except Exception as e:
            if "Failed to invoke procedure `apoc.import.json`" in str(e):
                return jsonify({'success': False, 'error': 'APOC extension not installed on Neo4j server.'}), 500
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'error': 'File import failed'}), 500

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, port=5001)
