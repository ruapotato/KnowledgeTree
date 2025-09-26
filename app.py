# app.py
import os
import uuid
import schedule
import time
import threading
import json
from urllib.parse import unquote, quote
from dotenv import load_dotenv, set_key
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, send_file
from neo4j import GraphDatabase, basic_auth
import markdown
from scripts.pull_freshservice import sync_companies_and_users
from scripts.pull_datto import sync_datto_devices
from scripts.pull_fresh_tickets import sync_fresh_tickets


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

def prime_database_schema(tx):
    """
    Creates and immediately deletes a dummy file node and relationship.
    This "primes" the database with the necessary labels and relationship types,
    preventing "UnknownLabelWarning" and "UnknownRelationshipTypeWarning"
    on a fresh database.
    """
    tx.run("""
        MERGE (dummy_parent:ContextItem {id: 'schema_primer_parent'})
        CREATE (dummy_file:File {id: 'schema_primer_file', filename: 'dummy.txt'})
        CREATE (dummy_parent)-[:HAS_FILE]->(dummy_file)
        DETACH DELETE dummy_parent, dummy_file
    """)

with driver.session() as session:
    session.write_transaction(ensure_root_exists)
    session.write_transaction(prime_database_schema)


# --- URL Generation Helper ---
@app.template_filter('quote_plus')
def quote_plus_filter(s):
    # This makes the URL encoding function available in Jinja templates
    return quote(s)

# --- Main Routes ---

@app.route('/')
def index():
    return redirect(url_for('browse'))

@app.route('/browse/', defaults={'path': ''})
@app.route('/browse/<path:path>')
def browse(path):
    path_parts = [p for p in path.split('/') if p]

    parent_path = "/".join([quote(part) for part in path_parts[:-1]])

    with driver.session() as session:
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

        children_query = """
            MATCH (:ContextItem {id: $parent_id})-[:PARENT_OF]->(child)
            RETURN DISTINCT child.id AS id, child.name AS name, child.is_folder AS is_folder,
                   child.is_attached as is_attached, child.read_only as read_only
            ORDER BY child.is_folder DESC, child.name
        """
        children_result = session.run(children_query, parent_id=node_id)
        items = [dict(record) for record in children_result]

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
                           current_node_id=node_id,
                           parent_path=parent_path)

@app.route('/view/<node_id>')
def view_node(node_id):
    with driver.session() as session:
        path_query = """
            MATCH p = shortestPath((:ContextItem {id: 'root'})-[:PARENT_OF*..]->(:ContextItem {id: $node_id}))
            RETURN [n IN nodes(p) | n.name] AS names
        """
        result = session.run(path_query, node_id=node_id).single()

        parent_path = ''
        if result and result['names']:
            parent_path_parts = result['names'][1:-1]
            parent_path = "/".join([quote(name) for name in parent_path_parts])

    return render_template('view.html', node_id=node_id, parent_path=parent_path)


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

# --- API Endpoints ---

@app.route('/api/search', methods=['GET'])
def search_nodes():
    query = request.args.get('query', '')
    start_node_id = request.args.get('start_node_id', 'root')

    if not query: return jsonify([])

    with driver.session() as session:
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
            path_list = record_dict['path_names'][1:]
            folder_path = "/".join([quote(name) for name in path_list])
            record_dict['folder_path'] = folder_path
            processed_results.append(record_dict)

        return jsonify(processed_results)

@app.route('/api/node', methods=['POST'])
def create_node():
    data = request.json
    parent_id = data.get('parent_id')
    name = data.get('name')
    is_folder = data.get('is_folder', False)
    is_attached = data.get('is_attached', False)

    if not all([parent_id, name]):
        return jsonify({'error': 'parent_id and name are required'}), 400

    new_id = str(uuid.uuid4())
    with driver.session() as session:
        session.run("""
            MATCH (parent:ContextItem {id: $parent_id})
            CREATE (child:ContextItem {
                id: $id,
                name: $name,
                is_folder: $is_folder,
                content: '',
                is_attached: $is_attached,
                read_only: false
            })
            CREATE (parent)-[:PARENT_OF]->(child)
        """, parent_id=parent_id, id=new_id, name=name, is_folder=is_folder, is_attached=is_attached)
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/node/<node_id>', methods=['GET'])
def get_node(node_id):
    def fetch_node(tx, node_id):
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
    elif job_name == 'freshtickets':
        overwrite = request.json.get('overwrite', False)
        threading.Thread(target=sync_fresh_tickets, args=(overwrite,)).start()
        return jsonify({'success': True, 'message': 'Freshservice ticket sync started.'})
    return jsonify({'success': False, 'error': 'Invalid job name.'}), 400

@app.route('/api/admin/export', methods=['GET'])
def export_user_data():
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH p = (:ContextItem {id:'root'})-[:PARENT_OF*..]->(n:ContextItem)
                WHERE (n.read_only IS NULL OR n.read_only = false) AND n.id <> 'root'
                RETURN [node IN nodes(p) | node.name] AS path_parts,
                       n.content AS content,
                       n.is_folder AS is_folder,
                       n.is_attached AS is_attached
            """)

            export_data = []
            for record in result:
                # The path includes 'KnowledgeTree Root', which we skip for the export path
                path = "/".join(record['path_parts'][1:])
                export_data.append({
                    "path": path,
                    "content": record['content'],
                    "is_folder": record['is_folder'],
                    "is_attached": record['is_attached']
                })

            export_file_path = "export.json"
            with open(export_file_path, 'w') as f:
                json.dump(export_data, f, indent=2)

            return send_file(export_file_path, as_attachment=True, download_name='knowledgetree_export.json')

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/import', methods=['POST'])
def import_user_data():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file:
        try:
            import_data = json.load(file)
            # Sort by path so that parent directories are processed before their children
            import_data.sort(key=lambda x: x['path'])

            with driver.session() as session:
                with session.begin_transaction() as tx:
                    for item in import_data:
                        path_parts = item['path'].split('/')
                        item_name = path_parts[-1]
                        parent_path_parts = path_parts[:-1]

                        # Find the parent node by traversing from the root
                        current_parent_id = 'root'
                        for folder_name in parent_path_parts:
                            result = tx.run(
                                "MATCH (parent:ContextItem {id: $parent_id})-[:PARENT_OF]->(child:ContextItem {name: $name}) RETURN child.id as id",
                                parent_id=current_parent_id, name=folder_name).single()

                            if result:
                                current_parent_id = result['id']
                            else:
                                # This error means the import file is missing a parent folder definition, or is not sorted correctly.
                                raise Exception(f"Inconsistent data: parent folder '{folder_name}' not found for item '{item_name}'.")

                        # Create or update the item itself
                        is_folder = item.get('is_folder', False)
                        # The 'is_attached' flag should only apply to folders
                        is_attached = item.get('is_attached', False) and is_folder
                        # Files have content, folders do not
                        content = item.get('content', '') if not is_folder else ''

                        # MERGE on the relationship pattern to correctly find or create the node.
                        # This is the idiomatic way to handle nodes that are unique per parent.
                        tx.run("""
                            MATCH (parent:ContextItem {id: $parent_id})
                            MERGE (parent)-[r:PARENT_OF]->(item:ContextItem {name: $name})
                            ON CREATE SET item.id = $id,
                                          item.is_folder = $is_folder,
                                          item.is_attached = $is_attached,
                                          item.content = $content,
                                          item.read_only = false
                            ON MATCH SET  item.is_folder = $is_folder,
                                          item.is_attached = $is_attached,
                                          item.content = $content
                        """, parent_id=current_parent_id, name=item_name, id=str(uuid.uuid4()),
                             is_folder=is_folder, is_attached=is_attached, content=content)

            return jsonify({'success': True, 'message': 'Import successful.'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'error': 'File import failed'}), 500

@app.route('/api/context/tree/<node_id>', methods=['GET'])
def get_context_tree(node_id):
    with driver.session() as session:
        # This query finds the direct path and then, for each node on that path,
        # finds any folders that are directly attached.
        path_query = """
            MATCH p = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            WITH nodes(p) AS path_nodes
            UNWIND path_nodes as ancestor
            MATCH (ancestor)-[:PARENT_OF]->(attached:ContextItem {is_attached: true})
            RETURN DISTINCT attached.id as id, attached.name as name
        """
        result = session.run(path_query, node_id=node_id)
        attached_folders = [dict(record) for record in result]
        return jsonify({'attached_folders': attached_folders})

@app.route('/api/context/<node_id>', methods=['GET', 'POST'])
def get_context(node_id):
    excluded_attached_ids = []
    if request.method == 'POST':
        data = request.json
        excluded_attached_ids = data.get('excluded_ids', [])

    all_context_blocks = []
    with driver.session() as session:
        path_query = """
            MATCH p = (:ContextItem {id: 'root'})-[:PARENT_OF*0..]->(:ContextItem {id: $node_id})
            RETURN nodes(p) AS path_nodes
        """
        result = session.run(path_query, node_id=node_id).single()
        if not result:
            return jsonify({'error': 'Node not found'}), 404

        path_nodes = result['path_nodes']

        for i, node in enumerate(path_nodes):
            # This query gets direct child articles AND articles from attached folders
            articles_query = """
                MATCH (folder:ContextItem {id: $folder_id})-[:PARENT_OF]->(child)
                WHERE NOT child.is_folder AND (child.is_attached IS NULL OR child.is_attached = false)
                RETURN child.id as id, child.name AS name, child.content AS content, "" AS source_folder
                UNION
                MATCH (folder:ContextItem {id: $folder_id})-[:PARENT_OF]->(attached:ContextItem {is_attached: true})
                WHERE NOT attached.id IN $excluded_ids
                MATCH (attached)-[:PARENT_OF*..]->(article:ContextItem)
                WHERE NOT article.is_folder
                RETURN article.id as id, article.name AS name, article.content AS content, attached.name AS source_folder
            """
            articles_result = session.run(articles_query, folder_id=node['id'], excluded_ids=excluded_attached_ids)

            content_block_items = []
            for record in articles_result:
                file_header = f"File: {record['name']}"
                if record['source_folder']:
                    file_header += f" (from attached folder: {record['source_folder']})"
                content_block_items.append(f"{file_header}\n\n{record['content'] or '> No content.'}")

            if content_block_items:
                all_context_blocks.append({
                    "header": f"Context: {node['name']}",
                    "content": "\n\n".join(content_block_items),
                    "depth": i + 1
                })

        final_context_parts = []
        for block in sorted(all_context_blocks, key=lambda x: x['depth']):
            heading = '#' * block['depth']
            final_context_parts.append(f"{heading} {block['header']}")
            final_context_parts.append(block['content'])

        files_query = """
            OPTIONAL MATCH (:ContextItem {id: $node_id})-[:HAS_FILE]->(f:File)
            RETURN f.filename as filename
        """
        files_result = session.run(files_query, node_id=node_id)
        filenames = [record['filename'] for record in files_result if record['filename'] is not None]
        if filenames:
            final_context_parts.append(f"## Attached Files for {path_nodes[-1]['name']}")
            final_context_parts.append("\n".join([f"- {name}" for name in filenames]))

    full_context = "\n\n".join(final_context_parts)
    return jsonify({'context': full_context})


if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(host='0.0.0.0', port=5001, debug=True)
