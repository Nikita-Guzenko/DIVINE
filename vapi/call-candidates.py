#!/usr/bin/env python3
"""
Divine CDL-A Recruiter - Batch Call Script
Calls candidates from the database using Vapi AI voice assistant.

Usage:
    python call-candidates.py                    # Call all "New" candidates
    python call-candidates.py --status "Team OK" # Call specific status
    python call-candidates.py --phone +1234567890 # Call single number
    python call-candidates.py --test             # Test call to your number
    python call-candidates.py --list             # List candidates to call
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

import requests

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "vapi-config.json")
DATABASE_PATH = os.path.join(SCRIPT_DIR, "..", "data", "candidates.db")

# Load Vapi config
with open(CONFIG_FILE) as f:
    config = json.load(f)

VAPI_KEY = config["private_key"]
ASSISTANT_ID = config["assistant_id"]
PHONE_NUMBER_ID = config["phone_number_id"]
VAPI_PHONE = config["phone_number"]

# Vapi API
VAPI_API = "https://api.vapi.ai"
HEADERS = {
    "Authorization": f"Bearer {VAPI_KEY}",
    "Content-Type": "application/json"
}


def get_candidates(status="New", limit=10):
    """Get candidates from database by status."""
    if not os.path.exists(DATABASE_PATH):
        print(f"Error: Database not found at {DATABASE_PATH}")
        return []

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, phone, email, status, created_at
        FROM candidates
        WHERE status = ? AND phone IS NOT NULL AND phone != ''
        ORDER BY created_at DESC
        LIMIT ?
    """, (status, limit))

    candidates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return candidates


def format_phone(phone):
    """Format phone number for Vapi (E.164 format)."""
    if not phone:
        return None

    # Remove all non-digits
    digits = ''.join(c for c in phone if c.isdigit())

    # Add +1 if US number without country code
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) > 10:
        return f"+{digits}"

    return None


def make_call(phone_number, candidate_name=None):
    """Initiate a call using Vapi."""
    formatted_phone = format_phone(phone_number)
    if not formatted_phone:
        print(f"  Error: Invalid phone number: {phone_number}")
        return None

    payload = {
        "phoneNumberId": PHONE_NUMBER_ID,
        "assistantId": ASSISTANT_ID,
        "customer": {
            "number": formatted_phone
        }
    }

    # Add candidate name to assistant overrides if available
    if candidate_name:
        payload["assistantOverrides"] = {
            "variableValues": {
                "candidateName": candidate_name
            }
        }

    try:
        response = requests.post(
            f"{VAPI_API}/call",
            headers=HEADERS,
            json=payload
        )

        if response.status_code == 201:
            call_data = response.json()
            return call_data
        else:
            print(f"  Error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"  Error making call: {e}")
        return None


def update_candidate_status(candidate_id, new_status, notes=None):
    """Update candidate status in database."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if notes:
        cursor.execute("""
            UPDATE candidates
            SET status = ?, notes = COALESCE(notes || '\n', '') || ?
            WHERE id = ?
        """, (new_status, notes, candidate_id))
    else:
        cursor.execute("""
            UPDATE candidates
            SET status = ?
            WHERE id = ?
        """, (new_status, candidate_id))

    conn.commit()
    conn.close()


def list_candidates(status="New"):
    """List candidates that would be called."""
    candidates = get_candidates(status, limit=100)

    if not candidates:
        print(f"No candidates found with status '{status}'")
        return

    print(f"\nCandidates with status '{status}':")
    print("-" * 60)

    for c in candidates:
        phone = format_phone(c['phone'])
        print(f"  {c['id']:4} | {c['name'][:25]:<25} | {phone or 'Invalid'}")

    print("-" * 60)
    print(f"Total: {len(candidates)} candidates")


def call_single(phone_number):
    """Make a single test call."""
    print(f"\nCalling {phone_number}...")

    result = make_call(phone_number)

    if result:
        print(f"  Call initiated!")
        print(f"  Call ID: {result.get('id')}")
        print(f"  Status: {result.get('status')}")
        print(f"\n  Monitor at: https://dashboard.vapi.ai/calls")
    else:
        print("  Failed to initiate call")


def call_candidates(status="New", limit=5, delay=30):
    """Call multiple candidates with delay between calls."""
    candidates = get_candidates(status, limit)

    if not candidates:
        print(f"No candidates found with status '{status}'")
        return

    print(f"\nPreparing to call {len(candidates)} candidates...")
    print(f"Delay between calls: {delay} seconds")
    print("-" * 60)

    for i, candidate in enumerate(candidates, 1):
        name = candidate['name']
        phone = candidate['phone']
        formatted = format_phone(phone)

        print(f"\n[{i}/{len(candidates)}] {name}")
        print(f"  Phone: {formatted}")

        if not formatted:
            print("  Skipping - invalid phone number")
            continue

        result = make_call(formatted, name)

        if result:
            call_id = result.get('id')
            print(f"  Call initiated! ID: {call_id}")

            # Update status in database
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            update_candidate_status(
                candidate['id'],
                "Calling",
                f"[{timestamp}] Vapi call initiated: {call_id}"
            )
        else:
            print("  Failed to initiate call")

        # Delay before next call (except for last one)
        if i < len(candidates):
            print(f"  Waiting {delay}s before next call...")
            time.sleep(delay)

    print("\n" + "-" * 60)
    print("Batch complete!")
    print(f"Monitor calls at: https://dashboard.vapi.ai/calls")


def main():
    parser = argparse.ArgumentParser(description="Divine CDL-A Recruiter - Batch Call Script")
    parser.add_argument("--status", default="New", help="Candidate status to call (default: New)")
    parser.add_argument("--limit", type=int, default=5, help="Max candidates to call (default: 5)")
    parser.add_argument("--delay", type=int, default=30, help="Seconds between calls (default: 30)")
    parser.add_argument("--phone", help="Call a single phone number")
    parser.add_argument("--test", action="store_true", help="Make a test call to 305-413-8988")
    parser.add_argument("--list", action="store_true", help="List candidates without calling")

    args = parser.parse_args()

    print("=" * 60)
    print("Divine CDL-A Recruiter - Vapi Voice Assistant")
    print(f"Outbound Number: {VAPI_PHONE}")
    print("=" * 60)

    if args.list:
        list_candidates(args.status)
    elif args.test:
        call_single("+13054138988")
    elif args.phone:
        call_single(args.phone)
    else:
        call_candidates(args.status, args.limit, args.delay)


if __name__ == "__main__":
    main()
