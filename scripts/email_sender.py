"""
Email Sender for Divine Recruiting
Sends templated emails to candidates
"""

import smtplib
import imaplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime
import re
import config
import database as db


class EmailSender:
    def __init__(self):
        self.smtp_connection = None
        self.template = self._load_template()
        self.prescreening_template = self._load_prescreening_template()

    def _load_prescreening_template(self) -> dict:
        """Load pre-screening email template"""
        template = {"subject": "", "body": ""}

        try:
            with open(config.PRESCREENING_TEMPLATE, 'r') as f:
                content = f.read()

            if "## Subject" in content:
                subject_start = content.find("## Subject") + len("## Subject")
                subject_end = content.find("## Body")
                template["subject"] = content[subject_start:subject_end].strip()

            if "## Body" in content:
                body_start = content.find("## Body") + len("## Body")
                template["body"] = content[body_start:].strip()

        except FileNotFoundError:
            print(f"Warning: Pre-screening template not found at {config.PRESCREENING_TEMPLATE}")
            template["subject"] = "CDL Team Driver - Divine Enterprises"
            template["body"] = "Hey {first_name},\n\nAre you open to team driving?\n\nNikita Guzenko\nDivine Enterprises"

        return template

    def _load_template(self) -> dict:
        """Load email template from file"""
        template = {"subject": "", "body": ""}

        try:
            with open(config.EMAIL_TEMPLATE, 'r') as f:
                content = f.read()

            # Parse subject
            if "## Subject" in content:
                subject_start = content.find("## Subject") + len("## Subject")
                subject_end = content.find("## Body")
                template["subject"] = content[subject_start:subject_end].strip()

            # Parse body
            if "## Body" in content:
                body_start = content.find("## Body") + len("## Body")
                template["body"] = content[body_start:].strip()

        except FileNotFoundError:
            print(f"Warning: Template not found at {config.EMAIL_TEMPLATE}")
            template["subject"] = "CDL Team Driver Opportunity - Divine Enterprises"
            template["body"] = "Please complete your application: {intelliapp_url}"

        return template

    def connect(self):
        """Connect to SMTP server"""
        if not config.EMAIL_ADDRESS or not config.EMAIL_PASSWORD:
            raise ValueError("Email credentials not configured in config.py")

        self.smtp_connection = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        self.smtp_connection.starttls()
        self.smtp_connection.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        print(f"Connected to SMTP server: {config.SMTP_SERVER}")

    def send_candidate_email(self, candidate: dict) -> bool:
        """Send email to a candidate"""
        if not self.smtp_connection:
            self.connect()

        # Prepare email content with candidate data
        subject = self.template["subject"]
        body = self.template["body"].format(
            first_name=candidate.get("first_name", "Driver"),
            last_name=candidate.get("last_name", ""),
            intelliapp_url=config.INTELLIAPP_URL,
            company_phone=config.COMPANY_PHONE
        )

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.EMAIL_ADDRESS
        msg["To"] = candidate["email"]

        # Plain text version
        msg.attach(MIMEText(body, "plain"))

        # Send
        try:
            self.smtp_connection.sendmail(
                config.EMAIL_ADDRESS,
                candidate["email"],
                msg.as_string()
            )
            print(f"Email sent to: {candidate['email']}")
            return True
        except Exception as e:
            print(f"Failed to send email to {candidate['email']}: {e}")
            return False

    def send_prescreening_email(self, candidate: dict) -> bool:
        """Send pre-screening email to check team driving willingness"""
        if not config.USE_DIVINE_EMAIL:
            print("Warning: Divine corporate email not configured. Set USE_DIVINE_EMAIL=True in config.py")
            print(f"Skipping: {candidate.get('first_name')} {candidate.get('last_name')}")
            return False

        if not self.smtp_connection:
            self.connect()

        subject = self.prescreening_template["subject"]
        body = self.prescreening_template["body"].format(
            first_name=candidate.get("first_name", "Driver")
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.SENDER_NAME} <{config.EMAIL_ADDRESS}>"
        msg["To"] = candidate["email"]

        msg.attach(MIMEText(body, "plain"))

        try:
            self.smtp_connection.sendmail(
                config.EMAIL_ADDRESS,
                candidate["email"],
                msg.as_string()
            )
            print(f"Pre-screening email sent to: {candidate['email']}")
            return True
        except Exception as e:
            print(f"Failed to send pre-screening email to {candidate['email']}: {e}")
            return False

    def process_unsent_candidates(self):
        """Read CSV and send emails to candidates who haven't received one"""
        candidates = []
        updated_candidates = []

        # Read current candidates
        try:
            with open(config.CANDIDATES_CSV, 'r') as f:
                reader = csv.DictReader(f)
                candidates = list(reader)
        except FileNotFoundError:
            print("No candidates file found")
            return

        # Process each candidate
        for candidate in candidates:
            if not candidate.get("email_sent_date") and candidate.get("email"):
                success = self.send_candidate_email(candidate)
                if success:
                    candidate["email_sent_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    candidate["status"] = "contacted"
            updated_candidates.append(candidate)

        # Write updated data back
        if updated_candidates:
            fieldnames = updated_candidates[0].keys()
            with open(config.CANDIDATES_CSV, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(updated_candidates)

        print(f"Processed {len(candidates)} candidates")

    def close(self):
        """Close SMTP connection"""
        if self.smtp_connection:
            self.smtp_connection.quit()
            print("SMTP connection closed")


def send_prescreening_to_new(candidate_id: int = None):
    """
    Send pre-screening emails to new candidates.
    If candidate_id specified, send only to that candidate.
    """
    sender = EmailSender()

    if candidate_id:
        candidate = db.get_candidate(candidate_id)
        if not candidate:
            print(f"Candidate {candidate_id} not found")
            return 0

        candidates = [candidate]
    else:
        candidates = db.get_candidates_for_screening()

    if not candidates:
        print("No candidates to screen")
        return 0

    print(f"Sending pre-screening emails to {len(candidates)} candidates...")

    sent_count = 0
    try:
        sender.connect()

        for candidate in candidates:
            name = f"{candidate['first_name']} {candidate['last_name']}"
            print(f"  {name}...", end=" ")

            if sender.send_prescreening_email(candidate):
                db.mark_screening_sent(candidate['id'])
                sent_count += 1
                print("✓")
            else:
                print("✗")

    finally:
        sender.close()

    print(f"\n✓ Sent {sent_count} pre-screening emails")
    return sent_count


def analyze_response(text: str) -> str:
    """
    Analyze response text to determine if candidate is open to team driving.
    Returns: 'Team OK', 'Solo Only', or 'Unclear'
    """
    text = text.lower()

    # Positive indicators
    positive = ['yes', 'yeah', 'yep', 'sure', 'open to', 'ok with', 'okay with',
                'have a partner', 'got a partner', 'my partner', 'interested',
                'i am', "i'm open", 'no problem', 'sounds good']

    # Negative indicators
    negative = ['no', 'solo', 'not interested', 'alone', 'by myself',
                "don't want", "cant", "can't", 'not open', 'prefer solo',
                'single', 'only solo']

    for word in positive:
        if word in text:
            return 'Team OK'

    for word in negative:
        if word in text:
            return 'Solo Only'

    return 'Unclear'


def check_replies():
    """
    Check IMAP inbox for replies to pre-screening emails.
    Updates candidate statuses based on responses.
    """
    print("Checking for pre-screening replies...")

    imap = imaplib.IMAP4_SSL(config.IMAP_SERVER, config.IMAP_PORT)
    imap.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
    imap.select("INBOX")

    # Search for replies to our prescreening email
    search_query = '(SUBJECT "Re: CDL Team Driver")'
    status, messages = imap.search(None, search_query)
    email_ids = messages[0].split()

    print(f"Found {len(email_ids)} potential replies")

    processed = 0
    candidates_waiting = {c['email'].lower(): c for c in db.get_candidates_awaiting_response()}

    for email_id in email_ids:
        status, msg_data = imap.fetch(email_id, "(RFC822)")
        msg = email_lib.message_from_bytes(msg_data[0][1])

        # Get sender email
        from_header = msg.get("From", "")
        sender_match = re.search(r'<([^>]+)>', from_header)
        sender_email = sender_match.group(1).lower() if sender_match else from_header.lower()

        # Check if this sender is a candidate awaiting response
        if sender_email not in candidates_waiting:
            continue

        candidate = candidates_waiting[sender_email]

        # Get email body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors='ignore')

        # Analyze response
        status = analyze_response(body)
        name = f"{candidate['first_name']} {candidate['last_name']}"

        if status == 'Unclear':
            print(f"  {name}: Unclear response, keeping in Screening")
            db.update_screening_response(candidate['id'], body[:500], 'Screening')
        else:
            print(f"  {name}: {status}")
            db.update_screening_response(candidate['id'], body[:500], status)
            processed += 1

        # Remove from waiting list to avoid re-processing
        del candidates_waiting[sender_email]

    imap.logout()
    print(f"\n✓ Processed {processed} replies")
    return processed


def main():
    """Main function - send emails to unsent candidates"""
    sender = EmailSender()

    try:
        sender.connect()
        sender.process_unsent_candidates()
    finally:
        sender.close()


if __name__ == "__main__":
    main()
