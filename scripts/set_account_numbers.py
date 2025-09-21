# scripts/set_account_numbers.py
import os
import sys
import requests
import base64
import time
import random
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
FRESHSERVICE_DOMAIN = os.getenv("FRESHSERVICE_DOMAIN")
API_KEY = os.getenv("FRESHSERVICE_API_KEY")
BASE_URL = f"https://{FRESHSERVICE_DOMAIN}"
ACCOUNT_NUMBER_FIELD = "account_number"
COMPANIES_PER_PAGE = 100
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds

def get_all_companies(headers):
    """Fetches all companies (departments) from the Freshservice API."""
    all_companies = []
    page = 1
    endpoint = f"{BASE_URL}/api/v2/departments"
    print(f"Fetching all companies from: {endpoint}")

    while True:
        params = {'page': page, 'per_page': COMPANIES_PER_PAGE}
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                print(f"Rate limit exceeded. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            data = response.json()
            companies_on_page = data.get('departments', [])
            if not companies_on_page:
                break
            all_companies.extend(companies_on_page)
            if len(companies_on_page) < COMPANIES_PER_PAGE:
                break
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching companies: {e}", file=sys.stderr)
            return None
    return all_companies

def update_company_account_number(headers, company_id, account_number):
    """Updates a single company with a new account number."""
    endpoint = f"{BASE_URL}/api/v2/departments/{company_id}"

    payload = {
        "custom_fields": {
            ACCOUNT_NUMBER_FIELD: account_number
        }
    }

    try:
        response = requests.put(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to update company ID {company_id}: {e}", file=sys.stderr)
        if hasattr(e, 'response'):
            print(f"Response: {e.response.text}", file=sys.stderr)
        return False

if __name__ == "__main__":
    print(" Freshservice Account Number Setter")
    print("==========================================")

    if not API_KEY or not FRESHSERVICE_DOMAIN:
        sys.exit("Error: FRESHSERVICE_DOMAIN and FRESHSERVICE_API_KEY must be set in the .env file.")

    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    companies = get_all_companies(headers)
    if companies is None:
        print("Could not fetch companies. Aborting.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFound {len(companies)} total companies in Freshservice.")

    existing_numbers = set()
    companies_to_update = []

    for company in companies:
        custom_fields = company.get('custom_fields', {})
        acc_num = custom_fields.get(ACCOUNT_NUMBER_FIELD)
        if acc_num:
            existing_numbers.add(int(acc_num))
        else:
            companies_to_update.append(company)

    print(f"Found {len(existing_numbers)} companies with existing account numbers.")
    print(f"Found {len(companies_to_update)} companies that need a new account number.")

    if not companies_to_update:
        print("\nAll companies already have an account number. Nothing to do.")
        sys.exit(0)

    print("\n--- Assigning New Account Numbers ---")
    updated_count = 0
    for company in companies_to_update:
        new_number = None
        while new_number is None or new_number in existing_numbers:
            new_number = random.randint(100000, 999999)

        company_id = company['id']
        company_name = company['name']

        print(f"Updating '{company_name}' (ID: {company_id}) with new account number: {new_number}")

        success = update_company_account_number(headers, company_id, new_number)

        if success:
            existing_numbers.add(new_number)
            updated_count += 1
            time.sleep(0.5)
        else:
            print(f"Skipping '{company_name}' due to update failure.")

    print("\n-----------------------------------------")
    print(f" Successfully updated {updated_count} companies.")
    print("\nScript finished.")
