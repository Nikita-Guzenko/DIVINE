#!/usr/bin/env python3
"""
iMessage Outreach Script for CDL-A Driver Candidates
Sends personalized messages with 2-minute intervals
"""

import subprocess
import sqlite3
import time
import random
from datetime import datetime

# Configuration
DB_PATH = "/Users/nikitaguzenko/Desktop/DIVINE/data/candidates.db"
MESSAGES_DB = "/Users/nikitaguzenko/Library/Messages/chat.db"
LOG_FILE = "/Users/nikitaguzenko/Desktop/DIVINE/logs/imessage_outreach.log"
INTERVAL_SECONDS = 120  # 2 minutes

# Candidates to skip (already in conversation)
SKIP_IDS = [18, 11]  # Gilbert Lopez, Blake Bumanglag

# Message variations
INTROS = [
    "This is Nikita from Divine Enterprises",
    "Nikita here from Divine Enterprises",
    "This is Nikita with Divine Enterprises",
    "Nikita from Divine here",
    "Nikita from Divine Enterprises here",
]

CORES = [
    "We received your application for CDL-A driver",
    "Got your CDL-A application",
    "Saw your CDL-A application",
    "Your CDL-A application came through",
    "Received your application for CDL-A driver",
]

QUESTIONS = [
    "Are you open for OTR team runs?",
    "Would you be open to OTR team driving?",
    "Interested in OTR team runs?",
    "Open to team driving OTR?",
    "Would you be interested in OTR team runs?",
]

def log(message):
    """Log message to file and print"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(LOG_FILE, "a") as f:
        f.write(log_line + "\n")

def format_phone(phone):
    """Convert 1916-317-8424 to +19163178424"""
    return "+" + phone.replace("-", "")

def generate_message(first_name):
    """Generate unique message for candidate"""
    name = first_name.title()
    intro = random.choice(INTROS)
    core = random.choice(CORES)
    question = random.choice(QUESTIONS)
    return f"Hi {name}. {intro}. {core}. {question}"

def send_imessage(phone, message):
    """Send iMessage via AppleScript"""
    script = f'''
    tell application "Messages"
        set targetBuddy to "{phone}"
        set targetService to 1st account whose service type = iMessage
        set theMessage to "{message}"
        send theMessage to buddy targetBuddy of targetService
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except Exception as e:
        log(f"  ERROR sending: {e}")
        return False

def check_delivery(phone, wait_seconds=5):
    """Check if message was delivered"""
    time.sleep(wait_seconds)
    phone_clean = phone.replace("+", "")

    conn = sqlite3.connect(MESSAGES_DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.is_delivered, m.is_sent
        FROM message m
        JOIN handle h ON m.handle_id = h.ROWID
        WHERE h.id LIKE ? AND m.is_from_me = 1
        ORDER BY m.date DESC LIMIT 1
    """, (f"%{phone_clean[-10:]}%",))

    result = cursor.fetchone()
    conn.close()

    if result:
        is_delivered, is_sent = result
        return {"delivered": bool(is_delivered), "sent": bool(is_sent)}
    return {"delivered": False, "sent": False}

def update_candidate_status(candidate_id):
    """Update candidate status to Screening"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE candidates
        SET call_status = 'Screening',
            screening_sent_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (candidate_id,))
    conn.commit()
    conn.close()

def get_candidates(limit=25):
    """Get NEW candidates from database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, first_name, last_name, phone
        FROM candidates
        WHERE call_status = 'New'
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    candidates = cursor.fetchall()
    conn.close()
    return candidates

def main():
    log("=" * 60)
    log("STARTING iMESSAGE OUTREACH")
    log("=" * 60)

    candidates = get_candidates(25)
    log(f"Found {len(candidates)} candidates")

    # Filter out skip IDs
    candidates = [c for c in candidates if c[0] not in SKIP_IDS]
    log(f"After filtering: {len(candidates)} candidates")

    sent_count = 0
    delivered_count = 0
    failed_count = 0

    for i, (cid, first_name, last_name, phone) in enumerate(candidates, 1):
        formatted_phone = format_phone(phone)
        message = generate_message(first_name)

        log(f"\n[{i}/{len(candidates)}] {first_name} {last_name}")
        log(f"  Phone: {formatted_phone}")
        log(f"  Message: {message}")

        # Send message
        success = send_imessage(formatted_phone, message)

        if success:
            sent_count += 1
            log(f"  SENT - checking delivery...")

            # Check delivery
            status = check_delivery(formatted_phone)
            if status["delivered"]:
                delivered_count += 1
                log(f"  DELIVERED via iMessage")
            elif status["sent"]:
                log(f"  SENT (delivery pending)")
            else:
                log(f"  SENT (status unknown)")

            # Update database
            update_candidate_status(cid)
            log(f"  Status updated to 'Screening'")
        else:
            failed_count += 1
            log(f"  FAILED to send")

        # Wait before next message (except for last one)
        if i < len(candidates):
            log(f"\n  Waiting {INTERVAL_SECONDS} seconds...")
            time.sleep(INTERVAL_SECONDS)

    # Summary
    log("\n" + "=" * 60)
    log("OUTREACH COMPLETE")
    log(f"  Total: {len(candidates)}")
    log(f"  Sent: {sent_count}")
    log(f"  Delivered: {delivered_count}")
    log(f"  Failed: {failed_count}")
    log("=" * 60)

if __name__ == "__main__":
    main()
