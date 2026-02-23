#!/usr/bin/env python3
import smtplib
import random
import time
import gspread
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.service_account import Credentials
from datetime import datetime

# Email config
EMAIL_ADDRESS = "nguzen@gmail.com"
EMAIL_PASSWORD = "jvoxlvfyambswels"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Email variations (subject, body)
VARIATIONS = [
    ("Quick question about your CDL application",
     "Hi {name},\n\nWe received your application for the CDL-A driver position at Divine Enterprises.\n\nQuick question - are you open to team driving?\n\nNikita Guzenko\nDivine Enterprises"),
    
    ("Divine Enterprises - CDL-A Position",
     "Hi {name},\n\nThanks for applying to Divine Enterprises!\n\nBefore we move forward - would you be interested in team driving opportunities?\n\nNikita Guzenko\nDivine Enterprises"),
    
    ("Your CDL-A application",
     "Hi {name},\n\nThis is Nikita from Divine Enterprises. We're reviewing your application.\n\nOne question - are team driving routes something you'd consider?\n\nNikita Guzenko\nDivine Enterprises"),
    
    ("Following up on your application",
     "Hi {name},\n\nWe got your CDL-A application at Divine Enterprises.\n\nQuick question - are you available for team runs?\n\nNikita Guzenko\nDivine Enterprises"),
    
    ("CDL-A opportunity at Divine Enterprises",
     "Hi {name},\n\nSaw your application for CDL-A driver. We have team positions available - would that work for you?\n\nNikita Guzenko\nDivine Enterprises"),
]

def send_email(to_email, subject, body):
    """Send email via Gmail SMTP"""
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
    return True

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open('/Users/nikitaguzenko/Desktop/DIVINE/email_log.txt', 'a') as f:
        f.write(line + '\n')

# Setup Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds_path = '/Users/nikitaguzenko/Desktop/DIVINE/scripts/google_credentials.json'
creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
client = gspread.authorize(creds)
SHEET_ID = '1mJoB8KQY7lOYWu8ONFUXZq9JYilpQPA0CVwYHOQeRBg'
spreadsheet = client.open_by_key(SHEET_ID)
sheet = spreadsheet.sheet1

# Get candidates with "New" status and email
all_values = sheet.get_all_values()
candidates = []
for i, row in enumerate(all_values[1:], 2):
    if len(row) >= 6 and row[5] == 'New':
        name = row[1] if len(row) > 1 else ''
        email = row[3] if len(row) > 3 else ''
        if name and email and '@' in email:
            candidates.append({
                'row': i,
                'name': name,
                'email': email,
                'first_name': name.split()[0] if name else ''
            })

# Send to first 10
log(f"Starting email campaign to {min(10, len(candidates))} candidates")
log("=" * 50)

ORANGE = {'red': 1.0, 'green': 0.85, 'blue': 0.5}  # Orange for Email

sent = 0
for i, c in enumerate(candidates[:10]):
    subject, body_template = VARIATIONS[i % 5]
    body = body_template.format(name=c['first_name'])
    
    log(f"[{i+1}/10] Sending to {c['name']} ({c['email']})...")
    
    try:
        send_email(c['email'], subject, body)
        sheet.update_cell(c['row'], 6, 'Email')  # Status
        sheet.format(f"A{c['row']}:P{c['row']}", {'backgroundColor': ORANGE})
        log(f"  ✓ Sent successfully, status updated to Email")
        sent += 1
    except Exception as e:
        log(f"  ✗ Failed: {e}")
    
    if i < 9:  # Don't wait after last email
        wait_time = random.randint(480, 600)  # 8-10 minutes in seconds
        log(f"  Waiting {wait_time//60} min {wait_time%60} sec...")
        time.sleep(wait_time)

log("=" * 50)
log(f"Campaign complete! Sent: {sent}/10")
