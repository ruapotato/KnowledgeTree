# scripts/pull_freshservice.py
import os
import sys
import requests
import base64
import time
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# --- Neo4j Connection ---
uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password))

# --- Freshservice Configuration ---
FRESHSERVICE_DOMAIN = os.getenv("FRESHSERVICE_DOMAIN")
API_KEY = os.getenv("FRESHSERVICE_API_KEY")
ACCOUNT_NUMBER_FIELD = "account_number" 

def get_freshservice_companies():
    """Fetches all companies from the Freshservice API."""
    all_companies = []
    page = 1
    endpoint = f"https://{FRESHSERVICE_DOMAIN}/api/v2/departments"
    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {encoded_auth}"}

    print("Fetching companies from Freshservice...")
    while True:
        try:
            params = {'page': page, 'per_page': 100}
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            companies_on_page = data.get('departments', [])
            if not companies_on_page:
                break
            all_companies.extend(companies_on_page)
            page += 1
            time.sleep(0.5) 
        except requests.exceptions.RequestException as e:
            print(f"Error fetching Freshservice companies: {e}", file=sys.stderr)
            return None
    print(f"Found {len(all_companies)} companies.")
    return all_companies

def get_freshservice_users():
    """Fetches all users (requesters) from the Freshservice API."""
    all_users = []
    page = 1
    endpoint = f"https://{FRESHSERVICE_DOMAIN}/api/v2/requesters"
    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {encoded_auth}"}

    print("Fetching users from Freshservice...")
    while True:
        try:
            params = {'page': page, 'per_page': 100}
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 5))
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            data = response.json()
            users_on_page = data.get('requesters', [])
            if not users_on_page:
                break
            all_users.extend(users_on_page)
            page += 1
            time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching Freshservice users: {e}", file=sys.stderr)
            return None
    print(f"Found {len(all_users)} users.")
    return all_users


def sync_companies_and_users():
    companies = get_freshservice_companies()
    users = get_freshservice_users()

    if not companies or not users:
        print("Could not fetch data from Freshservice. Aborting.")
        return

    # Create a mapping of Freshservice department ID to our account number
    fs_id_to_account_map = {}
    for company in companies:
        account_number = (company.get('custom_fields') or {}).get(ACCOUNT_NUMBER_FIELD)
        if account_number:
            fs_id_to_account_map[company['id']] = str(account_number)

    with driver.session() as session:
        # Create a 'Companies' root folder if it doesn't exist
        session.run("""
            MERGE (root:ContextItem {id: 'root'})
            MERGE (companies:ContextItem {id: 'companies_root', name: 'Companies', is_folder: true})
            MERGE (root)-[:PARENT_OF]->(companies)
        """)

        for company in companies:
            company_name = company.get('name')
            account_number = (company.get('custom_fields') or {}).get(ACCOUNT_NUMBER_FIELD)

            if not company_name or not account_number:
                continue

            # Create or update company folder and its own "Users" subfolder
            session.run("""
                MATCH (companies_root:ContextItem {id: 'companies_root'})
                MERGE (c:ContextItem {id: $account_number, name: $name, is_folder: true})
                SET c.freshservice_id = $fs_id
                MERGE (companies_root)-[:PARENT_OF]->(c)
                MERGE (u_root:ContextItem {id: 'users_for_' + $account_number, name: 'Users', is_folder: true})
                MERGE (c)-[:PARENT_OF]->(u_root)
            """, account_number=str(account_number), name=company_name, fs_id=company.get('id'))

        for user in users:
            if not user.get('active'):
                continue
            
            user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            user_email = user.get('primary_email')
            department_ids = user.get('department_ids')

            if not user_name or not user_email or not department_ids:
                continue

            for dept_id in department_ids:
                account_number = fs_id_to_account_map.get(dept_id)
                if account_number:
                    contact_md_content = f"""
# Contact Information for {user_name}

- **Email:** {user_email}
- **Title:** {user.get('job_title', 'N/A')}
- **Work Phone:** {user.get('work_phone_number', 'N/A')}
- **Mobile Phone:** {user.get('mobile_phone_number', 'N/A')}
- **Time Zone:** {user.get('time_zone', 'N/A')}
"""
                    # Correctly match the company's "Users" folder and create the user inside it
                    session.run("""
                        MATCH (users_root:ContextItem {id: 'users_for_' + $account_number})
                        MERGE (user_folder:ContextItem {id: $user_email, name: $user_name, is_folder: true, user_email: $user_email})
                        MERGE (users_root)-[:PARENT_OF]->(user_folder)
                        MERGE (contact_md:ContextItem {id: 'contact_for_' + $user_email, name: 'Contact.md', is_folder: false, user_email: $user_email})
                        ON CREATE SET contact_md.content = $content, contact_md.read_only = true
                        ON MATCH SET contact_md.content = $content, contact_md.read_only = true
                        MERGE (user_folder)-[:PARENT_OF]->(contact_md)
                    """, account_number=account_number, user_name=user_name, user_email=user_email, content=contact_md_content)
                    break 

if __name__ == "__main__":
    sync_companies_and_users()
    driver.close()
