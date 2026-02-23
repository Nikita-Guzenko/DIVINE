#!/usr/bin/env python3
"""
Divine Recruiting Automation - Main Runner

Commands:
    python run.py process      - Process new CDL candidates from Gmail
    python run.py sync         - Sync database to Google Sheet
    python run.py stats        - Show database statistics
    python run.py list         - List recent candidates
    python run.py search NAME  - Search candidates
"""

import sys
import argparse
import imaplib
import email
from email.header import decode_header
import re

import config
import database as db
from careerplug_scraper import CareerPlugScraper
from google_sheets import sync_to_sheet
from email_sender import send_prescreening_to_new, check_replies


def process_candidates(position_filter: str = "CDL"):
    """Process new candidates from Gmail notifications"""
    print("=" * 60)
    print(f"PROCESSING {position_filter.upper()} CANDIDATES")
    print("=" * 60)

    # Connect to Gmail
    print("\n1. Connecting to Gmail...")
    imap = imaplib.IMAP4_SSL(config.IMAP_SERVER, config.IMAP_PORT)
    imap.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
    imap.select("INBOX")

    # Search for emails
    search_query = f'(FROM "careerplug" SUBJECT "{position_filter}")'
    status, messages = imap.search(None, search_query)
    email_ids = messages[0].split()
    print(f"   Found {len(email_ids)} emails matching '{position_filter}'")

    # Parse emails
    candidates_to_process = []

    for email_id in email_ids:
        status, msg_data = imap.fetch(email_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors='ignore')

        urls = re.findall(r'https://email\.reply\.careerplug\.com/c/[^\s<>"\')\]]+', body)
        if urls:
            candidates_to_process.append({
                "subject": subject,
                "redirect_url": urls[0]
            })

    imap.logout()
    print(f"   Parsed {len(candidates_to_process)} valid candidates")

    if not candidates_to_process:
        print("\n   No new candidates to process")
        return 0

    # Process through CareerPlug
    print(f"\n2. Extracting data from CareerPlug...")
    scraper = CareerPlugScraper()
    added_count = 0

    try:
        scraper.start()

        for i, item in enumerate(candidates_to_process, 1):
            name = item['subject'].split(' - ')[0]
            print(f"   [{i}/{len(candidates_to_process)}] {name}...", end=" ")

            candidate = scraper.get_candidate_from_email_notification(
                item["subject"],
                item["redirect_url"]
            )

            candidate_id = db.add_candidate(candidate)
            if candidate_id:
                added_count += 1
                print("✓")
            else:
                print("(duplicate)")

    finally:
        scraper.close()

    print(f"\n✓ Added {added_count} new candidates")
    return added_count


def show_stats():
    """Show database statistics"""
    stats = db.get_stats()

    print("\n" + "=" * 40)
    print("DATABASE STATISTICS")
    print("=" * 40)
    print(f"  Total candidates:  {stats['total']}")
    print(f"  New (uncalled):    {stats['new']}")
    print(f"  Screening:         {stats['screening']}")
    print(f"  Team OK:           {stats['team_ok']}")
    print(f"  Solo Only:         {stats['solo_only']}")
    print(f"  Called:            {stats['called']}")
    print(f"  Emailed:           {stats['emailed']}")
    print(f"  Unsynced to sheet: {stats['unsynced']}")
    print("=" * 40)


def list_candidates(limit: int = 20):
    """List recent candidates"""
    candidates = db.get_candidates(limit=limit)

    print(f"\nLast {len(candidates)} candidates:")
    print("-" * 80)

    for c in candidates:
        name = f"{c['first_name']} {c['last_name']}"
        status = c['call_status'] or 'New'
        print(f"  {c['id']:3} | {name:25} | {c['phone']:15} | {status}")

    print("-" * 80)


def search_candidates(query: str):
    """Search candidates"""
    results = db.search_candidates(query)

    print(f"\nSearch results for '{query}': {len(results)} found")
    print("-" * 80)

    for c in results:
        name = f"{c['first_name']} {c['last_name']}"
        print(f"  ID: {c['id']}")
        print(f"  Name: {name}")
        print(f"  Email: {c['email']}")
        print(f"  Phone: {c['phone']}")
        print(f"  Position: {c['position']}")
        print(f"  Status: {c['call_status']}")
        print("-" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="Divine Recruiting Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py process           Process new CDL candidates
    python run.py process --all     Process ALL candidates (not just CDL)
    python run.py screen            Send pre-screening emails to New candidates
    python run.py screen --id 15    Send pre-screening to specific candidate
    python run.py check-replies     Check for replies to pre-screening emails
    python run.py sync              Sync to Google Sheet
    python run.py stats             Show statistics
    python run.py list              List recent candidates
    python run.py list --status "Team OK"  List by status
    python run.py search "John"     Search by name/email/phone
        """
    )

    parser.add_argument(
        "command",
        choices=["process", "sync", "stats", "list", "search", "screen", "check-replies"],
        help="Command to run"
    )

    parser.add_argument(
        "query",
        nargs="?",
        help="Search query (for search command)"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all candidates, not just CDL"
    )

    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="Limit for list command"
    )

    parser.add_argument(
        "--id",
        type=int,
        help="Candidate ID (for screen command)"
    )

    parser.add_argument(
        "--status",
        help="Filter by status (for list command)"
    )

    args = parser.parse_args()

    if args.command == "process":
        filter_term = "" if args.all else "CDL"
        added = process_candidates(filter_term if filter_term else "New Applicant")

        if added > 0:
            print("\n→ Run 'python run.py sync' to sync to Google Sheet")

    elif args.command == "sync":
        sync_to_sheet()

    elif args.command == "stats":
        show_stats()

    elif args.command == "list":
        if args.status:
            candidates = db.get_candidates(status=args.status, limit=args.limit)
            print(f"\nCandidates with status '{args.status}': {len(candidates)}")
            print("-" * 80)
            for c in candidates:
                name = f"{c['first_name']} {c['last_name']}"
                print(f"  {c['id']:3} | {name:25} | {c['phone']:15} | {c['email']}")
            print("-" * 80)
        else:
            list_candidates(args.limit)

    elif args.command == "search":
        if not args.query:
            print("Error: Search query required")
            print("Usage: python run.py search 'query'")
            sys.exit(1)
        search_candidates(args.query)

    elif args.command == "screen":
        sent = send_prescreening_to_new(args.id)
        if sent > 0:
            print("\n→ Run 'python run.py check-replies' to check for responses")

    elif args.command == "check-replies":
        processed = check_replies()
        if processed > 0:
            print("\n→ Run 'python run.py list --status \"Team OK\"' to see candidates ready for call")


if __name__ == "__main__":
    main()
