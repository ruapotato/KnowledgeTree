# scripts/test_ticket_dump.py
import os
import sys
import requests
import base64
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Freshservice Configuration ---
FRESHSERVICE_DOMAIN = os.getenv("FRESHSERVICE_DOMAIN")
API_KEY = os.getenv("FRESHSERVICE_API_KEY")

def get_ticket_and_conversations(ticket_id):
    """Fetches a single ticket and its conversations and prints the raw JSON."""
    if not all([FRESHSERVICE_DOMAIN, API_KEY]):
        print("Error: FRESHSERVICE_DOMAIN and FRESHSERVICE_API_KEY must be set in the .env file.")
        return

    # Prepare authentication
    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {encoded_auth}"}

    # --- Fetch the Ticket ---
    ticket_endpoint = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}"
    print(f"--- Fetching Ticket Data for Ticket #{ticket_id} ---")
    print(f"URL: {ticket_endpoint}\n")
    try:
        response = requests.get(ticket_endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        ticket_data = response.json()
        print(json.dumps(ticket_data, indent=2))
    except requests.exceptions.RequestException as e:
        print(f"Error fetching ticket data: {e}", file=sys.stderr)
        return

    # --- Fetch the Conversations ---
    conv_endpoint = f"https://{FRESHSERVICE_DOMAIN}/api/v2/tickets/{ticket_id}/conversations"
    print(f"\n\n--- Fetching Conversation Data for Ticket #{ticket_id} ---")
    print(f"URL: {conv_endpoint}\n")
    try:
        response = requests.get(conv_endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        conv_data = response.json()
        print(json.dumps(conv_data, indent=2))
    except requests.exceptions.RequestException as e:
        print(f"Error fetching conversation data: {e}", file=sys.stderr)
        if hasattr(e, 'response'):
             print(f"Response: {e.response.text}", file=sys.stderr)
        return


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_ticket_dump.py <TICKET_ID>")
        sys.exit(1)

    ticket_to_fetch = sys.argv[1]
    get_ticket_and_conversations(ticket_to_fetch)
