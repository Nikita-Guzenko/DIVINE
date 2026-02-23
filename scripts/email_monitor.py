# ⚠️ DEPRECATED: This file is not used. Use run.py instead.
"""
Email Monitor for CareerPlug Notifications
Monitors inbox for new candidate notifications and processes them
"""

import imaplib
import email
from email.header import decode_header
import re
import time
from datetime import datetime
import config
from careerplug_scraper import CareerPlugScraper
from email_sender import EmailSender


class EmailMonitor:
    def __init__(self):
        self.imap_connection = None
        self.scraper = None
        self.sender = None

    def connect(self):
        """Connect to IMAP server"""
        if not config.EMAIL_ADDRESS or not config.EMAIL_PASSWORD:
            raise ValueError("Email credentials not configured in config.py")

        self.imap_connection = imaplib.IMAP4_SSL(config.IMAP_SERVER, config.IMAP_PORT)
        self.imap_connection.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        print(f"Connected to IMAP server: {config.IMAP_SERVER}")

    def get_careerplug_notifications(self, unread_only=True) -> list:
        """Get CareerPlug notification emails"""
        notifications = []

        self.imap_connection.select("INBOX")

        # Search for CareerPlug emails
        search_criteria = '(FROM "careerplug")'
        if unread_only:
            search_criteria = f'(UNSEEN {search_criteria})'

        status, messages = self.imap_connection.search(None, search_criteria)

        if status != "OK":
            print("No messages found")
            return notifications

        email_ids = messages[0].split()
        print(f"Found {len(email_ids)} CareerPlug notifications")

        for email_id in email_ids:
            status, msg_data = self.imap_connection.fetch(email_id, "(RFC822)")

            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])

            # Decode subject
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8")

            # Get email body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode()
                        break
                    elif part.get_content_type() == "text/html":
                        body = part.get_payload(decode=True).decode()
            else:
                body = msg.get_payload(decode=True).decode()

            # Extract CareerPlug candidate URL from email
            urls = re.findall(r'https?://[^\s<>"]+careerplug[^\s<>"]+applicant[^\s<>"]+', body, re.I)

            if urls:
                notifications.append({
                    "email_id": email_id,
                    "subject": subject,
                    "candidate_url": urls[0],
                    "received_date": msg["Date"]
                })
                print(f"Found candidate URL: {urls[0]}")

        return notifications

    def mark_as_read(self, email_id):
        """Mark email as read"""
        self.imap_connection.store(email_id, '+FLAGS', '\\Seen')

    def process_notifications(self):
        """Main workflow: check notifications → scrape → send email"""
        # Initialize components
        self.scraper = CareerPlugScraper()
        self.sender = EmailSender()

        try:
            self.scraper.start()
            self.sender.connect()

            # Get new notifications
            notifications = self.get_careerplug_notifications(unread_only=True)

            for notification in notifications:
                print(f"\nProcessing: {notification['subject']}")

                # Scrape candidate data
                candidate = self.scraper.get_candidate_from_url(notification['candidate_url'])

                if candidate and candidate.get("email"):
                    # Save to CSV
                    self.scraper.save_candidate(candidate)

                    # Send email
                    success = self.sender.send_candidate_email(candidate)

                    if success:
                        # Update candidate status in CSV
                        candidate["email_sent_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        candidate["status"] = "contacted"

                    # Mark notification as read
                    self.mark_as_read(notification['email_id'])

                print(f"Processed: {candidate.get('first_name', 'Unknown')} {candidate.get('last_name', '')}")

            print(f"\nTotal processed: {len(notifications)} candidates")

        finally:
            self.scraper.close()
            self.sender.close()

    def run_continuous(self):
        """Run monitor continuously"""
        print(f"Starting continuous monitor (checking every {config.CHECK_INTERVAL_MINUTES} minutes)")
        print("Press Ctrl+C to stop\n")

        while True:
            try:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new candidates...")
                self.connect()
                self.process_notifications()
                self.close()

                print(f"Next check in {config.CHECK_INTERVAL_MINUTES} minutes...")
                time.sleep(config.CHECK_INTERVAL_MINUTES * 60)

            except KeyboardInterrupt:
                print("\nStopping monitor...")
                break
            except Exception as e:
                print(f"Error: {e}")
                print("Retrying in 1 minute...")
                time.sleep(60)

    def close(self):
        """Close IMAP connection"""
        if self.imap_connection:
            self.imap_connection.logout()
            print("IMAP connection closed")


def main():
    """Main function"""
    monitor = EmailMonitor()

    try:
        monitor.connect()
        # Single run
        monitor.process_notifications()
        # Or continuous monitoring:
        # monitor.run_continuous()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
