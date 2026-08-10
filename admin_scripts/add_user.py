import requests
import base64
import argparse
import os
from dotenv import load_dotenv
load_dotenv()

# EDITED 02/11/26: Removed email hard code, specify email in command line.
"""
Invitation Management Script
This script sends invitation requests to the WIC API to invite users to specific groups.
It accepts one or more email addresses as command-line arguments and sends individual
invitation requests for each email. 
Usages:
    python add_user.py email1@example.com email2@example.com
    python add_user.py user@domain.org
    python add_user.py user@domain.org -t <api_token>
    python add_user.py email1@example.com email2@example.com -t <api_token>
"""
url = "https://tayamni.spa.umn.edu/api/invitations"
token = f'token {os.environ["API_KEY"]}'

def parse_args():
    parser = argparse.ArgumentParser(description='add a user')
    parser.add_argument("emails", nargs="+", help='Email(s) to be invited')
    parser.add_argument("-t", nargs="?", type=str, default=None, help="api token to be used")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    
    if args.t == None:
        print("No API token provided, using default...")
        headers = {
            "Content-Type": "application/json",
            "Authorization": token
        }
    else:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"token {args.t}"
        }
    
    # Use the emails from command-line arguments
    for email in args.emails:
        payload = {
            "userEmail": email,
            "roles": ["Full user"],
            "groupIDs": [5, 6, 7, 8]
        }
        response = requests.post(url, json=payload, headers=headers, verify=os.environ['cert_path'])
        print(response.json())