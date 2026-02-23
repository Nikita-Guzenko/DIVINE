"""
Google Sheets Sync for Divine Recruiting
Syncs SQLite database to Google Sheets
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import database as db

# Configuration
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'google_credentials.json')
SPREADSHEET_ID = "1mJoB8KQY7lOYWu8ONFUXZq9JYilpQPA0CVwYHOQeRBg"


class GoogleSheetsSync:
    def __init__(self):
        self.gc = None
        self.spreadsheet = None
        self.worksheet = None

    def connect(self):
        """Connect to Google Sheets"""
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=SCOPES
        )
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open_by_key(SPREADSHEET_ID)
        self.worksheet = self.spreadsheet.sheet1
        print(f"✓ Connected to: {self.spreadsheet.title}")

    def get_existing_phones(self) -> set:
        """Get set of all phone numbers already in sheet"""
        all_data = self.worksheet.get_all_values()
        phones = set()
        for row in all_data[1:]:  # Skip header
            if len(row) > 2 and row[2]:
                phone = db.normalize_phone(row[2])
                if phone:
                    phones.add(phone)
        return phones

    def sync_candidates(self) -> int:
        """
        Sync unsynced candidates from SQLite to Google Sheet
        Returns count of synced candidates
        """
        # Get unsynced candidates
        candidates = db.get_unsynced_candidates()

        if not candidates:
            print("  No new candidates to sync")
            return 0

        print(f"  Found {len(candidates)} candidates to sync")

        # Get existing phones to avoid duplicates
        existing_phones = self.get_existing_phones()

        synced_ids = []
        rows_to_add = []

        for c in candidates:
            phone_normalized = db.normalize_phone(c.get('phone', ''))

            # Skip if already in sheet
            if phone_normalized in existing_phones:
                print(f"    → Skip (already in sheet): {c['first_name']} {c['last_name']}")
                synced_ids.append(c['id'])  # Mark as synced anyway
                continue

            # Prepare row matching sheet columns:
            # 1. Date Called
            # 2. Applicant Name
            # 3. Phone Number
            # 4. Call Status
            # 5. Comment
            # 6. Call Back Number
            # 7. Class A Experience
            # 8. Open to Team Driving?
            # 9. Reason for Switching
            # 10. Days on Road
            # 11. Expected Home Time
            # 12. 53' Temp exp
            # 13. Doubles/Triples
            # 14. Tanker
            # 15. Hazmat
            # 16. W-2 or 1099

            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()

            # Build comment
            comment_parts = []
            if c.get('position'):
                comment_parts.append(f"Applied: {c['position']}")
            if c.get('location'):
                comment_parts.append(f"Loc: {c['location']}")
            if c.get('email'):
                comment_parts.append(f"Email: {c['email']}")
            if c.get('comment'):
                comment_parts.append(c['comment'])

            row = [
                c.get('date_called', ''),           # Date Called
                name,                                # Applicant Name
                c.get('phone', ''),                 # Phone Number
                c.get('call_status', 'New'),        # Call Status
                ". ".join(comment_parts),           # Comment
                c.get('phone', ''),                 # Call Back Number
                c.get('experience_years', ''),      # Class A Experience
                c.get('open_to_team', ''),          # Open to Team Driving?
                c.get('reason_switching', ''),      # Reason for Switching
                c.get('days_on_road', ''),          # Days on Road
                c.get('home_time', ''),             # Expected Home Time
                c.get('temp_controlled_exp', ''),   # 53' Temp exp
                c.get('endorsement_doubles', ''),   # Doubles/Triples
                c.get('endorsement_tanker', ''),    # Tanker
                c.get('endorsement_hazmat', ''),    # Hazmat
                c.get('employment_type', ''),       # W-2 or 1099
            ]

            rows_to_add.append(row)
            synced_ids.append(c['id'])
            existing_phones.add(phone_normalized)

            print(f"    ✓ {name}")

        # Batch add rows
        if rows_to_add:
            self.worksheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')

        # Mark as synced in database
        if synced_ids:
            db.mark_synced(synced_ids)

        print(f"\n  ✓ Synced {len(rows_to_add)} new candidates to Google Sheet")
        return len(rows_to_add)


def sync_to_sheet():
    """Main sync function"""
    print("\n" + "=" * 50)
    print("SYNCING TO GOOGLE SHEET")
    print("=" * 50)

    gs = GoogleSheetsSync()
    gs.connect()

    count = gs.sync_candidates()

    print("=" * 50)
    return count


if __name__ == "__main__":
    sync_to_sheet()
