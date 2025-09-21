# app.py
import os
import uuid
import schedule
import time
import threading
import json
from urllib.parse import unquote
from dotenv import load_dotenv, set_key
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, send_file
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

# --- Scheduler ---
def run_continuously(interval=1):
    cease_continuous_run = threading.Event()

    class ScheduleThread(threading.Thread):
        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)

    continuous_thread = ScheduleThread()
    continuous_thread.start()
    return cease_continuous_run

def setup_scheduler():
    freshservice_interval = int(os.getenv('FRESHSERVICE_PULL_INTERVAL', 1440))
    datto_interval = int(os.getenv('DATTO_PULL_INTERVAL', 1440))

    schedule.every(freshservice_interval).minutes.do(sync_companies_and_users).tag('freshservice')
    schedule.every(datto_interval).minutes.do(sync_datto_devices).tag('datto')

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

# --- Admin Routes ---
@app.route('/admin')
def admin_panel():
    settings = {
        'FRESHSERVICE_PULL_INTERVAL': os.getenv('FRESHSERVICE_PULL_INTERVAL', 1440),
        'DATTO_PULL_INTERVAL': os.getenv('DATTO_PULL_INTERVAL', 1440)
    }
    return render_template('admin.html', settings=settings)

@app.route('/admin/settings')
def admin_settings():
    return redirect('/admin')

# --- API Endpoints ---
@app.route('/api/search', methods=['GET'])
def search_nodes():
    query = request.args.get('query', '')
    start_node_id = request.args.get('start_node_id', 'root')

    if not query:
        return jsonify([])

    with driver.session() as session:
        # This query now uses native Cypher to find descendant nodes
        # instead of relying on the APOC plugin.
        result = session.run("""
            MATCH (startNode:ContextItem {id: $start_node_id})-[:PARENT_OF*0..]->(node)
            WHERE toLower(node.name) CONTAINS toLower($query) OR toLower(node.content) CONTAINS toLower($query)
            RETURN node.id as id, node.name as name, node.is_folder as is_folder
            LIMIT 25
            """, {'start_node_id': start_node_id, 'query': query})
        return jsonify([dict(record) for record in result])

@app.route('/api/resolve_path', methods=['POST'])
def resolve_path():
    path_parts = request.json.get('path', [])
    if not path_parts:
        return jsonify({'id': 'root'})
    with driver.session() as session:
        query = "MATCH (n0:ContextItem {id: 'root'})"
        match_clauses = []
        where_clauses = []
        params = {}
        for i, part in enumerate(path_parts):
            prev_node, curr_node = f"n{i}", f"n{i+1}"
            param_name = f"part_{i}"
            match_clauses.append(f"MATCH ({prev_node})-[:PARENT_OF]->({curr_node})")
            where_clauses.append(f"{curr_node}.name = ${param_name}")
            params[param_name] = part
        full_query = "\n".join([query] + match_clauses) + "\nWHERE " + " AND ".join(where_clauses) + f"\nRETURN n{len(path_parts)}.id as id"
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
            RETURN DISTINCT child.id AS id, child.name AS name, child.is_folder AS is_folder, child.is_attached as is_attached, child.read_only as read_only
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
        RETURN n.id AS id, n.name AS name, n.content AS content, n.is_folder AS is_folder, n.is_attached as is_attached, n.read_only as read_only,
               collect({id: f.id, filename: f.filename}) AS files
        """
        result = tx.run(query, node_id=node_id).single()
        if result:
            data = dict(result)
            content = data.get('content') or ''
            data['content_html'] = markdown.markdown(content, extensions=['fenced_code', 'tables'])
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
        parent_is_attached_result = session.run("MATCH (p:ContextItem {id: $id}) RETURN p.is_attached as attached", id=parent_id).single()
        if parent_is_attached_result and parent_is_attached_result['attached'] and is_folder and not is_attached:
            return jsonify({'error': 'Only attached folders or knowledge articles can be created here.'}), 400
        session.run("""
            MATCH (parent:ContextItem {id: $parent_id})
            CREATE (child:ContextItem {id: $id, name: $name, is_folder: $is_folder, content: '', is_attached: $is_attached, read_only: false})
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
    def fetch_context_ordered(tx, node_id):
        path_query = """
            MATCH path = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            RETURN nodes(path) as path_nodes
        """
        path_result = tx.run(path_query, node_id=node_id).single()
        if not path_result:
            return []

        ordered_ancestors = path_result['path_nodes']
        
        full_context_data = []
        current_path_slug = ""

        for node in ordered_ancestors:
            ancestor_id = node['id']
            node_name = node['name']
            node_content = node.get('content', '')

            if ancestor_id == 'root':
                current_path_slug = f"/{node_name}"
            else:
                path_parts = current_path_slug.split(' / ')
                if path_parts[-1] != node_name:
                    current_path_slug += f" / {node_name}"

            if node_content and node_content.strip():
                full_context_data.append({
                    "path": current_path_slug,
                    "content": node_content
                })

            attached_content_query = """
                MATCH (ancestor:ContextItem {id: $ancestor_id})-[:PARENT_OF]->(attached_folder:ContextItem {is_attached: true})
                MATCH (attached_folder)-[:PARENT_OF*0..]->(article)
                WHERE article.is_folder = false AND article.content IS NOT NULL AND article.content <> ""
                RETURN article.name as name, article.content as content
            """
            attached_results = tx.run(attached_content_query, ancestor_id=ancestor_id)
            for record in attached_results:
                attached_path = f"{current_path_slug} (attached: {record['name']})"
                full_context_data.append({
                    "path": attached_path,
                    "content": record['content']
                })
        return full_context_data

    with driver.session() as session:
        context_data = session.read_transaction(fetch_context_ordered, node_id)
        
        output_parts = []
        for item in context_data:
            header = f"### Path: `{item['path']}`"
            content = item['content']
            output_parts.append(f"{header}\n\n{content}")
            
        full_context = "\n\n---\n\n".join(output_parts)
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

@app.route('/api/admin/save_settings', methods=['POST'])
def save_settings():
    settings = request.json
    for key, value in settings.items():
        set_key('.env', key, value)
    
    schedule.clear()
    setup_scheduler()
    
    return jsonify({'success': True, 'message': 'Settings saved and scheduler updated.'})

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
        with driver.session() as session:
            # This query finds all nodes and relationships that are NOT read-only
            # and exports them to a file on the server.
            result = session.run("""
                MATCH (n) WHERE n.read_only IS NULL OR n.read_only = false
                OPTIONAL MATCH (n)-[r]->(m) WHERE m.read_only IS NULL OR m.read_only = false
                WITH COLLECT(n) as nodes, COLLECT(r) as rels
                CALL apoc.export.json.data(nodes, rels, 'export.json', {stream: true})
                YIELD file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done, data
                RETURN file
            """).single()

            if result and result['file']:
                # The file is saved on the server by APOC. Now, send it to the client.
                return send_file("export.json", as_attachment=True, download_name='knowledgetree_export.json')
            else:
                 return jsonify({'success': False, 'error': 'Export failed or produced no data.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/import', methods=['POST'])
def import_user_data():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file:
        try:
            # Save the uploaded file temporarily to be accessed by Neo4j
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'import_data.json')
            file.save(file_path)

            with driver.session() as session:
                # Use APOC to import the JSON file
                # The file path needs to be absolute for Neo4j to find it
                session.run(f"""
                    CALL apoc.import.json("file://{os.path.abspath(file_path)}")
                """)

            os.remove(file_path) # Clean up the temporary file
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'error': 'File import failed'}), 500

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    setup_scheduler()
    stop_run_continuously = run_continuously()
    
    app.run(debug=True, port=5001)
    
    stop_run_continuously.set()
