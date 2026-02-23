#!/usr/bin/env python3
import subprocess
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# Message variations
VARIATIONS = [
    "Hi {name}, we received your application for the CDL-A driver position. Are you open to team driving?\n\nNikita Guzenko, Divine Enterprises",
    "Hi {name}, thanks for applying to Divine Enterprises! Quick question - are you open to team driving?\n\nNikita Guzenko, Divine Enterprises",
    "Hi {name}, this is Nikita from Divine Enterprises. We got your CDL-A application. Would you be interested in team driving?\n\nNikita Guzenko, Divine Enterprises",
    "Hi {name}, Divine Enterprises here. We're reviewing your CDL-A application. Are you available for team runs?\n\nNikita Guzenko, Divine Enterprises",
    "Hi {name}, Nikita from Divine Enterprises. Saw your application for CDL-A driver. Are team driving routes something you'd consider?\n\nNikita Guzenko, Divine Enterprises",
]

def send_imessage(phone, message):
    """Send iMessage using AppleScript"""
    script = f'''
    tell application "Messages"
        set targetBuddy to "+{phone}"
        set targetService to 1st account whose service type = iMessage
        set targetMessage to "{message}"
        send targetMessage to participant targetBuddy of targetService
    end tell
    '''
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    return result.returncode == 0

def update_sheet_status(sheet, row, status):
    """Update status in Google Sheet"""
    sheet.update_cell(row, 6, status)  # Column F

def log(msg):
    """Log message to file and print"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open('/Users/nikitaguzenko/Desktop/DIVINE/sms_log.txt', 'a') as f:
        f.write(line + '\n')

# Setup Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds_path = '/Users/nikitaguzenko/Desktop/DIVINE/scripts/google_credentials.json'
creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
client = gspread.authorize(creds)
SHEET_ID = '1mJoB8KQY7lOYWu8ONFUXZq9JYilpQPA0CVwYHOQeRBg'
sheet = client.open_by_key(SHEET_ID).sheet1

# Get candidates
all_values = sheet.get_all_values()
candidates = []
for i, row in enumerate(all_values[1:], 2):
    if len(row) >= 6 and row[5] == 'New':
        name = row[1] if len(row) > 1 else ''
        phone = row[2] if len(row) > 2 else ''
        if name and phone:
            phone_clean = ''.join(c for c in phone if c.isdigit())
            if len(phone_clean) == 10:
                phone_clean = '1' + phone_clean
            candidates.append({
                'row': i,
                'name': name,
                'phone': phone_clean,
                'first_name': name.split()[0] if name else ''
            })

# Send to first 25
log(f"Starting SMS campaign to {min(25, len(candidates))} candidates")
log("=" * 50)

sent = 0
for i, c in enumerate(candidates[:25]):
    variation = VARIATIONS[i % 5]
    message = variation.format(name=c['first_name'])
    
    log(f"[{i+1}/25] Sending to {c['name']} ({c['phone']})...")
    
    if send_imessage(c['phone'], message):
        update_sheet_status(sheet, c['row'], 'SMS')
        log(f"  ✓ Sent successfully, status updated to SMS")
        sent += 1
    else:
        log(f"  ✗ Failed to send")
    
    if i < 24:  # Don't wait after last message
        log(f"  Waiting 2 minutes...")
        time.sleep(120)

log("=" * 50)
log(f"Campaign complete! Sent: {sent}/25")
