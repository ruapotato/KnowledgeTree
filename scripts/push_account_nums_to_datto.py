# scripts/push_account_nums_to_datto.py
import os
import sys
import requests
import base64
import time
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
FRESHSERVICE_DOMAIN = os.getenv("FRESHSERVICE_DOMAIN")
FRESHSERVICE_API_KEY = os.getenv("FRESHSERVICE_API_KEY")
DATTO_API_ENDPOINT = os.getenv("DATTO_API_ENDPOINT")
DATTO_API_KEY = os.getenv("DATTO_API_KEY")
DATTO_API_SECRET = os.getenv("DATTO_API_SECRET")
ACCOUNT_NUMBER_FIELD = "account_number"
DATTO_VARIABLE_NAME = "AccountNumber"
REDBARN_KEYWORD = "Redbarn"
REDBARN_FRESHSERVICE_TARGET = "Redbarn Cannabis"

def get_freshservice_companies(headers):
    """Fetches all companies from the Freshservice API."""
    all_companies = []
    page = 1
    endpoint = f"https://{FRESHSERVICE_DOMAIN}/api/v2/departments"
    print("Fetching companies from Freshservice...")
    while True:
        try:
            params = {'page': page, 'per_page': 100}
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            companies_on_page = data.get('departments', [])
            if not companies_on_page: break
            all_companies.extend(companies_on_page)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching Freshservice companies: {e}", file=sys.stderr)
            return None
    print(f" Found {len(all_companies)} companies in Freshservice.")
    return all_companies

def get_datto_access_token():
    token_url = f"{DATTO_API_ENDPOINT}/auth/oauth/token"
    payload = {'grant_type': 'password', 'username': DATTO_API_KEY, 'password': DATTO_API_SECRET}
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Basic cHVibGljLWNsaWVudDpwdWJsaWM='}
    try:
        response = requests.post(token_url, headers=headers, data=payload, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Error getting Datto access token: {e}", file=sys.stderr)
        return None

def get_datto_sites(access_token):
    print("\nFetching sites from Datto RMM...")
    request_url = f"{DATTO_API_ENDPOINT}/api/v2/account/sites"
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        response = requests.get(request_url, headers=headers, timeout=30)
        response.raise_for_status()
        sites_data = response.json().get('sites', [])
        print(f" Found {len(sites_data)} sites in Datto RMM.")
        return sites_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Datto sites: {e}", file=sys.stderr)
        return None

def check_datto_variable_exists(access_token, site_uid, variable_name):
    """Checks if a specific variable already exists for a site."""
    request_url = f"{DATTO_API_ENDPOINT}/api/v2/site/{site_uid}/variables"
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        response = requests.get(request_url, headers=headers, timeout=30)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        variables = response.json().get("variables", [])
        for var in variables:
            if var.get("name") == variable_name:
                return True # The variable exists
        return False # The variable does not exist
    except requests.exceptions.RequestException as e:
        print(f"   -> ⚠️  Warning: Could not check for existing variables on site {site_uid}: {e}", file=sys.stderr)
        return True

def update_datto_site_variable(access_token, site_uid, variable_name, variable_value):
    """Pushes a variable value to a specific Datto RMM site."""
    request_url = f"{DATTO_API_ENDPOINT}/api/v2/site/{site_uid}/variable"
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    payload = {"name": variable_name, "value": str(variable_value)}
    try:
        response = requests.put(request_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"   -> ❌ FAILED to update Datto site {site_uid}: {e}", file=sys.stderr)
        if hasattr(e, 'response'):
             print(f"   -> Response: {e.response.text}", file=sys.stderr)
        return False

if __name__ == "__main__":
    print(" Datto RMM & Freshservice Account Number Pusher")
    print("===================================================")

    if not all([FRESHSERVICE_API_KEY, FRESHSERVICE_DOMAIN, DATTO_API_ENDPOINT, DATTO_API_KEY, DATTO_API_SECRET]):
        sys.exit("Error: All Freshservice and Datto environment variables must be set.")

    auth_str = f"{FRESHSERVICE_API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    fs_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    fs_companies = get_freshservice_companies(fs_headers)
    datto_token = get_datto_access_token()

    if not fs_companies or not datto_token:
        sys.exit("Could not fetch data from one or both services. Aborting.")

    datto_sites = get_datto_sites(datto_token)
    if not datto_sites:
        sys.exit("Could not fetch sites from Datto RMM. Aborting.")

    fs_company_map = {c.get('name').strip(): c for c in fs_companies if c.get('name')}

    actions_to_take = []
    unmapped_datto_sites = []

    for site in datto_sites:
        datto_name = (site.get('name') or '').strip()
        datto_uid = site.get('uid')
        fs_name_match = None

        if REDBARN_KEYWORD in datto_name:
            fs_name_match = REDBARN_FRESHSERVICE_TARGET
        else:
            best_match = ''
            for fs_name in fs_company_map.keys():
                if fs_name in datto_name and len(fs_name) > len(best_match):
                    best_match = fs_name
            if best_match:
                fs_name_match = best_match

        if fs_name_match:
            company_data = fs_company_map.get(fs_name_match)
            if company_data:
                account_number = company_data.get('custom_fields', {}).get(ACCOUNT_NUMBER_FIELD)
                actions_to_take.append({"datto_site_name": datto_name, "datto_site_uid": datto_uid, "account_number": account_number})
            else:
                unmapped_datto_sites.append(datto_name)
        else:
            unmapped_datto_sites.append(datto_name)

    print("\n---  Pushing Account Numbers to Datto RMM Sites ---")
    success_count, fail_count, already_set_count = 0, 0, 0
    for action in sorted(actions_to_take, key=lambda x: x['datto_site_name']):
        datto_name, datto_uid, acc_num = action['datto_site_name'], action['datto_site_uid'], action['account_number']

        if not acc_num:
            print(f"-> Skipping '{datto_name}': Account Number is MISSING in Freshservice.")
            continue

        print(f"-> Processing site '{datto_name}'...")

        if check_datto_variable_exists(datto_token, datto_uid, DATTO_VARIABLE_NAME):
            print("   ->   Skipping: 'AccountNumber' variable already exists.")
            already_set_count += 1
            continue

        print(f"   -> Pushing Account Number '{acc_num}'...")
        success = update_datto_site_variable(datto_token, datto_uid, DATTO_VARIABLE_NAME, acc_num)
        if success:
            success_count += 1
            print("   ->  Success.")
        else:
            fail_count +=1
        time.sleep(0.5)

    print("\n--- Summary ---")
    print(f"Successfully created/updated variables for {success_count} sites.")
    print(f"Skipped {already_set_count} sites that already had the variable set.")
    if fail_count > 0:
        print(f"Failed to update {fail_count} sites. Please check the logs above.")

    print("\n--- Unmapped Datto Sites (Ignored) ---")
    if unmapped_datto_sites:
        for name in sorted(unmapped_datto_sites):
            print(name)
    else:
        print("All mappable Datto sites were processed!")

    print("\nScript finished.")
