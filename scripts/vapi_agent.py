"""
VAPI Voice Agent — "Nikita" CDL Recruiter
Manages the AI voice agent for Divine Enterprises driver recruiting.

Usage:
    python vapi_agent.py call +13055551234 "John Smith"     # Call one candidate
    python vapi_agent.py call-new                            # Call all New candidates from Supabase
    python vapi_agent.py status <call_id>                    # Check call status
    python vapi_agent.py list-calls                          # List recent calls
    python vapi_agent.py test +13054138988                   # Test call to yourself
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import requests

# VAPI Configuration
VAPI_PRIVATE_KEY = os.environ.get("VAPI_PRIVATE_KEY", "")
VAPI_PUBLIC_KEY = os.environ.get("VAPI_PUBLIC_KEY", "")
VAPI_BASE_URL = "https://api.vapi.ai"
ASSISTANT_ID = os.environ.get("VAPI_ASSISTANT_ID", "551bd98f-92c0-4078-9df9-acc273de9340")
PHONE_NUMBER_ID = os.environ.get("VAPI_PHONE_ID", "01466fc8-7957-419e-aa08-9ffcdd7c203e")
PHONE_NUMBER = "+19166024938"

# Twilio config (for SMS)
TWILIO_SID = os.environ.get("TWILIO_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN", "")
TWILIO_FROM = PHONE_NUMBER

# IntelliApp link
INTELLIAPP_URL = "https://intelliapp.driverapponline.com/c/divinetrans"

# Supabase config
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "Authorization": f"Bearer {VAPI_PRIVATE_KEY}",
    "Content-Type": "application/json"
}


def make_call(phone_number: str, candidate_name: str) -> dict:
    """Make an outbound call to a candidate."""
    # Ensure phone number is in E.164 format
    if not phone_number.startswith("+"):
        phone_number = "+1" + phone_number.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")

    payload = {
        "assistantId": ASSISTANT_ID,
        "phoneNumberId": PHONE_NUMBER_ID,
        "customer": {
            "number": phone_number
        },
        "assistantOverrides": {
            "variableValues": {
                "candidate_name": candidate_name
            }
        }
    }

    resp = requests.post(f"{VAPI_BASE_URL}/call", json=payload, headers=HEADERS)

    if resp.status_code == 201:
        data = resp.json()
        print(f"Call initiated!")
        print(f"  Call ID: {data.get('id')}")
        print(f"  To: {phone_number} ({candidate_name})")
        print(f"  Status: {data.get('status')}")
        return data
    else:
        print(f"Error: {resp.status_code}")
        print(resp.json())
        return {}


def send_intelliapp_sms(phone_number: str, candidate_name: str):
    """Send IntelliApp link via SMS after a successful call."""
    if not phone_number.startswith("+"):
        phone_number = "+1" + phone_number.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")

    first_name = candidate_name.split()[0] if candidate_name else "there"

    message = (
        f"Hi {first_name}, this is Nikita from Divine Enterprises. "
        f"As we discussed on the phone, here is the link to your driver application: "
        f"{INTELLIAPP_URL} — "
        f"Please fill it out and I will run a background check. "
        f"Once approved, we will set up your orientation. "
        f"Call me if you have any questions. Thank you!"
    )

    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
        auth=(TWILIO_SID, TWILIO_TOKEN),
        data={"From": TWILIO_FROM, "To": phone_number, "Body": message}
    )

    if resp.status_code == 201:
        print(f"  SMS sent to {phone_number}!")
    else:
        print(f"  SMS failed: {resp.json().get('message', '')}")


def get_call_status(call_id: str) -> dict:
    """Get the status and details of a call."""
    resp = requests.get(f"{VAPI_BASE_URL}/call/{call_id}", headers=HEADERS)

    if resp.status_code == 200:
        data = resp.json()
        print(f"Call: {call_id}")
        print(f"  Status: {data.get('status')}")
        print(f"  Duration: {data.get('duration', 'N/A')}s")
        print(f"  Ended Reason: {data.get('endedReason', 'N/A')}")

        # Print transcript if available
        messages = data.get('messages') or data.get('artifact', {}).get('messages', [])
        if messages:
            print(f"\n  Transcript:")
            for msg in messages:
                role = msg.get('role', '?').upper()
                content = msg.get('message') or msg.get('content', '')
                if content:
                    print(f"    {role}: {content}")

        # Print recording URL if available
        recording = data.get('recordingUrl') or data.get('artifact', {}).get('recordingUrl')
        if recording:
            print(f"\n  Recording: {recording}")

        return data
    else:
        print(f"Error: {resp.status_code}")
        print(resp.json())
        return {}


def list_calls(limit: int = 20) -> list:
    """List recent calls."""
    resp = requests.get(f"{VAPI_BASE_URL}/call", headers=HEADERS, params={"limit": limit})

    if resp.status_code == 200:
        calls = resp.json()
        print(f"{'ID':<40} {'Status':<12} {'Duration':<10} {'Customer':<16} {'Ended Reason'}")
        print("-" * 100)
        for call in calls:
            call_id = call.get('id', '?')[:38]
            status = call.get('status', '?')
            duration = f"{call.get('duration', 'N/A')}s"
            customer = call.get('customer', {}).get('number', '?')
            ended = call.get('endedReason', '')
            print(f"{call_id:<40} {status:<12} {duration:<10} {customer:<16} {ended}")
        return calls
    else:
        print(f"Error: {resp.status_code}")
        print(resp.json())
        return []


def call_new_candidates():
    """Fetch 'New' candidates from Supabase and call them."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables required")
        print("Set them or pass candidates manually: python vapi_agent.py call +1234567890 'Name'")
        return

    supabase_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    # Fetch candidates with status 'New' or 'Call Again Later'
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/candidates",
        headers=supabase_headers,
        params={
            "select": "id,first_name,last_name,phone,status",
            "or": "(status.eq.New,status.eq.Call Again Later)",
            "phone": "not.is.null",
            "order": "created_at.desc",
            "limit": "50"
        }
    )

    if resp.status_code != 200:
        print(f"Supabase error: {resp.status_code}")
        print(resp.text)
        return

    candidates = resp.json()
    if not candidates:
        print("No candidates with 'New' or 'Call Again Later' status found.")
        return

    print(f"Found {len(candidates)} candidates to call:\n")
    for i, c in enumerate(candidates, 1):
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        phone = c.get('phone', 'N/A')
        status = c.get('status', '?')
        print(f"  {i}. {name} — {phone} [{status}]")

    print(f"\nReady to call {len(candidates)} candidates.")
    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    results = []
    for c in candidates:
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        phone = c.get('phone')
        if not phone:
            print(f"  Skipping {name} — no phone number")
            continue

        print(f"\nCalling {name} at {phone}...")
        result = make_call(phone, name)
        if result:
            results.append({
                "candidate_id": c['id'],
                "call_id": result.get('id'),
                "name": name,
                "phone": phone
            })
            # Update status to "AI Calling"
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/candidates",
                headers=supabase_headers,
                params={"id": f"eq.{c['id']}"},
                json={"status": "AI Calling"}
            )

        # Rate limit: wait between calls
        time.sleep(2)

    print(f"\n{'='*60}")
    print(f"Called {len(results)} candidates.")
    for r in results:
        print(f"  {r['name']}: Call ID {r['call_id']}")


def test_call(phone_number: str):
    """Make a test call to yourself."""
    print("Making test call...")
    print(f"  Agent will call: {phone_number}")
    print(f"  From: {PHONE_NUMBER}")
    print(f"  Agent will say: 'Hi, can I speak with Test Candidate?'")
    print()
    return make_call(phone_number, "Test Candidate")


def main():
    parser = argparse.ArgumentParser(description="VAPI Voice Agent — Divine Recruiting")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # call command
    call_parser = subparsers.add_parser("call", help="Call a specific candidate")
    call_parser.add_argument("phone", help="Phone number (E.164 or US format)")
    call_parser.add_argument("name", help="Candidate name")

    # call-new command
    subparsers.add_parser("call-new", help="Call all New candidates from Supabase")

    # status command
    status_parser = subparsers.add_parser("status", help="Check call status")
    status_parser.add_argument("call_id", help="VAPI call ID")

    # list-calls command
    list_parser = subparsers.add_parser("list-calls", help="List recent calls")
    list_parser.add_argument("--limit", type=int, default=20, help="Number of calls to show")

    # send-link command
    link_parser = subparsers.add_parser("send-link", help="Send IntelliApp link via SMS")
    link_parser.add_argument("phone", help="Phone number")
    link_parser.add_argument("name", help="Candidate name")

    # test command
    test_parser = subparsers.add_parser("test", help="Make a test call")
    test_parser.add_argument("phone", help="Your phone number for testing")

    args = parser.parse_args()

    if args.command == "call":
        make_call(args.phone, args.name)
    elif args.command == "call-new":
        call_new_candidates()
    elif args.command == "status":
        get_call_status(args.call_id)
    elif args.command == "list-calls":
        list_calls(args.limit)
    elif args.command == "send-link":
        send_intelliapp_sms(args.phone, args.name)
    elif args.command == "test":
        test_call(args.phone)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
