# scripts/pull_fresh_tickets.py
import os
import sys
import requests
import base64
import time
import re
from dotenv import load_dotenv
from neo4j import GraphDatabase
from markdownify import markdownify as md

load_dotenv()

# --- Neo4j Connection ---
uri = os.getenv("NEO_URI", os.getenv("NEO4J_URI"))
user = os.getenv("NEO_USER", os.getenv("NEO4J_USER"))
password = os.getenv("NEO_PASSWORD", os.getenv("NEO4J_PASSWORD"))
driver = GraphDatabase.driver(uri, auth=(user, password))

# --- Freshservice Configuration ---
FRESHSERVICE_DOMAIN = os.getenv("FRESHSERVICE_DOMAIN")
API_KEY = os.getenv("FRESHSERVICE_API_KEY")
STARTING_TICKET_ID = 550

# --- Mappings for Status and Priority ---
STATUS_MAP = {2: "Open", 3: "Pending", 4: "Resolved", 5: "Closed"}
PRIORITY_MAP = {1: "Low", 2: "Medium", 3: "High", 4: "Urgent"}

def get_freshservice_api(endpoint_with_params):
    """Generic function to handle GET requests to the Freshservice API."""
    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {encoded_auth}"}
    url = f"https://{FRESHSERVICE_DOMAIN}{endpoint_with_params}"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 15))
            print(f"Rate limit hit. Waiting for {retry_after} seconds.")
            time.sleep(retry_after)
            return get_freshservice_api(endpoint_with_params) # Retry
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from {url}: {e}", file=sys.stderr)
        return None

def get_latest_stored_ticket_id(session):
    """Queries the database to find the highest ticket ID currently stored."""
    result = session.run("""
        MATCH (t:ContextItem)
        WHERE t.id STARTS WITH 'ticket_'
        RETURN toInteger(substring(t.id, 7)) AS ticket_num
        ORDER BY ticket_num DESC
        LIMIT 1
    """).single()
    return result['ticket_num'] if result else STARTING_TICKET_ID -1

def get_new_ticket_ids_since(latest_id):
    """Efficiently finds only ticket IDs newer than the latest one we have."""
    new_ids = []
    page = 1
    print(f"Database contains tickets up to #{latest_id}. Checking for newer ones...")
    while True:
        endpoint = f"/api/v2/tickets?page={page}&per_page=100&order_by=created_at&order_type=desc"
        data = get_freshservice_api(endpoint)
        if not data or 'tickets' not in data or not data['tickets']:
            break

        found_older_ticket = False
        for ticket in data['tickets']:
            if ticket['id'] > latest_id:
                new_ids.append(ticket['id'])
            else:
                found_older_ticket = True
                break

        if found_older_ticket:
            break

        page += 1
        time.sleep(0.5)

    print(f"Found {len(new_ids)} new tickets to process.")
    return new_ids

def get_all_ticket_ids_for_overwrite():
    """Gets all ticket IDs for a full refresh."""
    all_ids = []
    page = 1
    print("Overwrite enabled: fetching all ticket IDs since the beginning.")
    while True:
        endpoint = f"/api/v2/tickets?page={page}&per_page=100&order_by=created_at&order_type=asc"
        data = get_freshservice_api(endpoint)
        if not data or 'tickets' not in data or not data['tickets']:
            break

        page_ids = [t['id'] for t in data['tickets'] if t['id'] >= STARTING_TICKET_ID]
        all_ids.extend(page_ids)

        if not page_ids or len(page_ids) < 100:
            break
        page += 1
    print(f"Found {len(all_ids)} total tickets to process for overwrite.")
    return all_ids

def sanitize_filename(name):
    """Removes invalid characters from a string so it can be used as a filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def get_user_email_for_requester(session, requester_id):
    """Finds a user's email in the DB from their Freshservice requester ID."""
    result = session.run("MATCH (u:ContextItem) WHERE u.freshservice_requester_id = $id RETURN u.user_email as email", id=requester_id).single()
    return result['email'] if result else None

def sync_fresh_tickets(overwrite=False):
    with driver.session() as session:
        ticket_ids_to_process = []
        if overwrite:
            ticket_ids_to_process = get_all_ticket_ids_for_overwrite()
        else:
            latest_id = get_latest_stored_ticket_id(session)
            ticket_ids_to_process = get_new_ticket_ids_since(latest_id)

        if not ticket_ids_to_process:
            print("No new tickets to sync.")
            return

        for ticket_id in sorted(ticket_ids_to_process):
            ticket_id_str = str(ticket_id)
            node_id = f"ticket_{ticket_id_str}"

            print(f"Processing Ticket #{ticket_id_str}...")

            ticket_data = get_freshservice_api(f"/api/v2/tickets/{ticket_id_str}")
            if not ticket_data or 'ticket' not in ticket_data:
                print(f"  - FAILED to get full details for #{ticket_id_str}")
                continue

            ticket = ticket_data['ticket']

            requester_id = ticket.get('requester_id')
            if not requester_id:
                print(f"  - Skipping: No requester ID found.")
                continue

            user_email = get_user_email_for_requester(session, requester_id)
            if not user_email:
                print(f"  - Skipping: User with FS ID {requester_id} is inactive or not in the database.")
                continue

            conversations_data = get_freshservice_api(f"/api/v2/tickets/{ticket_id_str}/conversations")
            conversations = conversations_data.get('conversations', []) if conversations_data else []

            ticket_subject = ticket.get('subject', 'No Subject')
            sanitized_subject = sanitize_filename(ticket_subject)
            ticket_filename = f"{ticket_id_str}_{sanitized_subject}.md"

            description_html = ticket.get('description', '> No description provided.')
            description_md = md(description_html, heading_style="ATX") if description_html else '> No description provided.'

            conversation_md_parts = []
            for conv in conversations:
                sender_name = conv.get('user', {}).get('name', 'Unknown')
                timestamp = conv.get('created_at', 'No Timestamp')
                body_html = conv.get('body', '> No content.')
                body_md = md(body_html, heading_style="ATX") if body_html else '> No content.'
                conversation_md_parts.append(f"### From: {sender_name} at `{timestamp}`\n\n{body_md}\n\n---")

            conversation_md = "\n".join(conversation_md_parts)

            status_name = STATUS_MAP.get(ticket.get('status'), 'N/A')
            priority_name = PRIORITY_MAP.get(ticket.get('priority'), 'N/A')
            agent_name = ticket.get('responder', {}).get('name', 'N/A') # Correctly get agent name from ticket data

            ticket_md_content = f"""
# Ticket #{ticket_id}: {ticket_subject}

- **Status:** {status_name}
- **Priority:** {priority_name}
- **Source:** {ticket.get('source_name', 'N/A')}
- **Created At:** {ticket.get('created_at')}
- **Agent:** {agent_name}
- **Group:** {ticket.get('group', {}).get('name', 'N/A')}

## Description

{description_md}

## Conversations

{conversation_md if conversation_md else "> No conversations found."}
"""

            session.run("""
                MATCH (user_folder:ContextItem {user_email: $user_email})
                MERGE (tickets_folder:ContextItem {id: 'tickets_for_' + $user_email, name: 'Tickets', is_folder: true, is_attached: true})
                MERGE (user_folder)-[:PARENT_OF]->(tickets_folder)

                MERGE (ticket_md:ContextItem {id: $node_id})
                ON CREATE SET ticket_md.name = $filename, ticket_md.is_folder = false, ticket_md.content = $content, ticket_md.read_only = true
                ON MATCH SET ticket_md.name = $filename, ticket_md.content = $content
                MERGE (tickets_folder)-[:PARENT_OF]->(ticket_md)
            """, user_email=user_email, node_id=node_id, filename=ticket_filename, content=ticket_md_content)
            print(f"  - Synced '{ticket_filename}' for {user_email}")
            time.sleep(0.2) # Be nice to the API

if __name__ == "__main__":
    should_overwrite = len(sys.argv) > 1 and sys.argv[1].lower() == 'overwrite'
    sync_fresh_tickets(overwrite=should_overwrite)
    driver.close()

