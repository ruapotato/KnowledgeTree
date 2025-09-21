# scripts/pull_datto.py
import os
import sys
import requests
import json
import time
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# --- Neo4j Connection ---
uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")
driver = GraphDatabase.driver(uri, auth=(user, password))

# --- Datto RMM Configuration ---
DATTO_ENDPOINT = os.getenv("DATTO_API_ENDPOINT")
DATTO_API_KEY = os.getenv("DATTO_API_KEY")
DATTO_API_SECRET = os.getenv("DATTO_API_SECRET")
DATTO_VARIABLE_NAME = "AccountNumber"

def get_datto_access_token():
    token_url = f"{DATTO_ENDPOINT}/auth/oauth/token"
    payload = {'grant_type': 'password', 'username': DATTO_API_KEY, 'password': DATTO_API_SECRET}
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Basic cHVibGljLWNsaWVudDpwdWJsaWM='}
    try:
        response = requests.post(token_url, headers=headers, data=payload, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Error getting Datto access token: {e}", file=sys.stderr)
        return None

def get_paginated_api_request(access_token, api_request_path):
    all_items = []
    next_page_url = f"{DATTO_ENDPOINT}/api{api_request_path}"
    headers = {'Authorization': f'Bearer {access_token}'}
    while next_page_url:
        try:
            response = requests.get(next_page_url, headers=headers, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            items_on_page = response_data.get('items') or response_data.get('sites') or response_data.get('devices')
            if items_on_page is None: break
            all_items.extend(items_on_page)
            next_page_url = response_data.get('pageDetails', {}).get('nextPageUrl') or response_data.get('nextPageUrl')
            time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            print(f"An error occurred during paginated API request for {api_request_path}: {e}", file=sys.stderr)
            return None
    return all_items
    
def get_site_variable(access_token, site_uid, variable_name):
    request_url = f"{DATTO_ENDPOINT}/api/v2/site/{site_uid}/variables"
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        response = requests.get(request_url, headers=headers, timeout=30)
        if response.status_code == 404: return None
        response.raise_for_status()
        variables = response.json().get("variables", [])
        for var in variables:
            if var.get("name") == variable_name:
                return var.get("value")
        return None
    except requests.exceptions.RequestException:
        return None

def find_user_for_device(session, company_id, device_hostname, device_description):
    """
    Attempts to associate a device with a user based on hostname or description.
    """
    # 1. Check for full name in description
    users_in_company = session.run("""
        MATCH (:ContextItem {id: $company_id})-[:PARENT_OF]->(:ContextItem {name: 'Users'})-[:PARENT_OF]->(u:ContextItem)
        RETURN u.name as name, u.user_email as email
    """, company_id=company_id)

    user_list = [dict(record) for record in users_in_company]

    for user in user_list:
        if user['name'].lower() in device_description.lower():
            return user['email']

    # 2. Check for unique first name in description
    first_names = [user['name'].split()[0].lower() for user in user_list]
    for user in user_list:
        first_name = user['name'].split()[0].lower()
        if first_name in device_description.lower() and first_names.count(first_name) == 1:
            return user['email']
            
    # 3. Check for unique first name in hostname
    for user in user_list:
        first_name = user['name'].split()[0].lower()
        if first_name in device_hostname.lower() and first_names.count(first_name) == 1:
            return user['email']

    return None

def sync_datto_devices():
    token = get_datto_access_token()
    if not token:
        sys.exit("\nFailed to obtain access token from Datto.")

    sites = get_paginated_api_request(token, "/v2/account/sites")
    if sites is None:
        sys.exit("\nCould not retrieve sites list from Datto.")
    print(f"\nFound {len(sites)} total sites in Datto.")

    with driver.session() as session:
        for site in sites:
            site_uid = site.get('uid')
            account_number = get_site_variable(token, site_uid, DATTO_VARIABLE_NAME)
            
            if not account_number:
                continue

            print(f"Processing site: {site.get('name')} (Account: {account_number})")
            devices = get_paginated_api_request(token, f"/v2/site/{site_uid}/devices")
            if not devices:
                continue

            for device in devices:
                hostname = device.get('hostname', 'Unknown Device')
                description = device.get('description', '')
                user_email = find_user_for_device(session, str(account_number), hostname, description)

                if user_email:
                    computer_md_content = f"""
# Computer Information: {hostname}

- **Operating System:** {device.get('operatingSystem', 'N/A')}
- **Device Type:** {(device.get('deviceType') or {}).get('category', 'N/A')}
- **Internal IP:** {device.get('intIpAddress', 'N/A')}
- **External IP:** {device.get('extIpAddress', 'N/A')}
- **Last Logged In User:** {device.get('lastLoggedInUser', 'N/A')}
- **Status:** {'Online' if device.get('online') else 'Offline'}
- **Last Seen:** {device.get('lastSeen')}
"""
                    session.run("""
                        MATCH (user_folder:ContextItem {user_email: $user_email})
                        MERGE (computer_md:ContextItem {name: $hostname, is_folder: false, datto_uid: $datto_uid})
                        ON CREATE SET computer_md.content = $content
                        ON MATCH SET computer_md.content = $content
                        MERGE (user_folder)-[:PARENT_OF]->(computer_md)
                    """, user_email=user_email, hostname=f"{hostname}.md", datto_uid=device.get('uid'), content=computer_md_content)
                    print(f"  - Associated '{hostname}' with user '{user_email}'")


if __name__ == "__main__":
    sync_datto_devices()
    driver.close()
