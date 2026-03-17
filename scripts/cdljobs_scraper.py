"""
CDLjobs.com Application Scraper
Extracts candidate data from CDLjobs.com admin panel using Playwright
"""

import os
from playwright.sync_api import sync_playwright
from typing import Optional, List, Dict


# CDLjobs credentials
CDLJOBS_URL = "https://www.cdljobs.com/administrator"
CDLJOBS_EMAIL = os.environ.get("CDLJOBS_EMAIL", "")
CDLJOBS_PASSWORD = os.environ.get("CDLJOBS_PASSWORD", "")
CARRIER_ADMIN_ID = "1075"

# Experience dropdown value mapping
EXPERIENCE_MAP = {
    "1": "Less than 3 Months",
    "2": "3-5 Months",
    "3": "6-11 Months",
    "4": "1 Year",
    "5": "2 Years",
    "6": "3+ Years",
}

# Checkbox label mappings
LICENSE_LABELS = ["Class A", "Class C", "Class B"]
DRIVER_TYPE_LABELS = ["Company Driver", "Lease Purchase", "Owner Operator", "Team"]
FREIGHT_LABELS = [
    "Auto Hauling", "Double/Triples", "Drop Deck", "Dry Van",
    "Flatbed", "HHG", "Reefer", "Specialized", "Tanker", "Other", "None"
]


class CDLJobsScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self.logged_in = False

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        print("Browser started")

    def login(self):
        print("Logging into CDLjobs.com...")
        self.page.goto(f"{CDLJOBS_URL}/index.php", wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(2000)

        # Fill login form
        username_field = self.page.query_selector('input[name="username"]')
        password_field = self.page.query_selector('input[name="passwd"]')

        if not username_field or not password_field:
            # Try alternative selectors
            username_field = self.page.query_selector('#mod-login-username, #username')
            password_field = self.page.query_selector('#mod-login-password, #passwd')

        if username_field and password_field:
            username_field.fill(CDLJOBS_EMAIL)
            password_field.fill(CDLJOBS_PASSWORD)
            # Click login button
            login_btn = self.page.query_selector('button[type="submit"], input[type="submit"]')
            if login_btn:
                login_btn.click()
            self.page.wait_for_timeout(3000)

        if "index.php" in self.page.url and "login" not in self.page.url.lower():
            self.logged_in = True
            print("✓ Logged into CDLjobs.com")
        else:
            raise Exception("Failed to login to CDLjobs.com")

    def get_application_ids(self) -> List[str]:
        """Get all application IDs from the applications list page."""
        if not self.logged_in:
            self.login()

        # Navigate to applications list
        url = (f"{CDLJOBS_URL}/index.php?option=com_jobs&view=applications"
               f"&carrierAdmin={CARRIER_ADMIN_ID}")
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            self.page.wait_for_timeout(3000)
        self.page.wait_for_timeout(2000)

        # Set limit to 500 to show all applications on one page
        self.page.select_option('#list_limit', '500')
        self.page.wait_for_timeout(4000)

        # Extract IDs from "View Application" links
        ids = self.page.eval_on_selector_all(
            'a[href*="application.edit"]',
            """elements => elements.map(a => {
                const match = a.href.match(/id=(\\d+)/);
                return match ? match[1] : null;
            }).filter(Boolean)"""
        )

        print(f"✓ Found {len(ids)} applications")
        return ids

    def get_application(self, app_id: str) -> Dict:
        """Extract all data from a single application page."""
        if not self.logged_in:
            self.login()

        url = (f"{CDLJOBS_URL}/index.php?option=com_jobs"
               f"&task=application.edit&id={app_id}")
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            self.page.wait_for_timeout(3000)
        self.page.wait_for_timeout(2000)
        # Verify we're on the right page
        if f"id={app_id}" not in self.page.url and 'application' not in self.page.url:
            # Retry navigation
            self.page.goto(url, wait_until="load", timeout=60000)
            self.page.wait_for_timeout(2000)

        candidate = self.page.evaluate("""() => {
            const val = id => {
                const el = document.getElementById(id);
                return el ? el.value.trim() : '';
            };
            const selText = id => {
                const el = document.getElementById(id);
                return el ? el.options[el.selectedIndex].text : '';
            };
            const checked = name => {
                const labels = {
                    'jform[LicenseTypeBit][]': ['Class A', 'Class C', 'Class B'],
                    'jform[DriverTypeBit][]': ['Company Driver', 'Lease Purchase', 'Owner Operator', 'Team'],
                    'jform[FreightTypeBit][]': ['Auto Hauling', 'Double/Triples', 'Drop Deck', 'Dry Van', 'Flatbed', 'HHG', 'Reefer', 'Specialized', 'Tanker', 'Other', 'None']
                };
                const cbs = document.querySelectorAll('input[name="' + name + '"]');
                const result = [];
                const lbls = labels[name] || [];
                cbs.forEach((cb, i) => { if (cb.checked) result.push(lbls[i] || cb.value); });
                return result;
            };

            return {
                cdljobs_id: val('jform_id'),
                first_name: val('jform_NameFirst'),
                last_name: val('jform_NameLast'),
                email: val('jform_EmailAddress'),
                phone: val('jform_Phone'),
                address: val('jform_Address1'),
                address2: val('jform_Address2'),
                city: val('jform_City'),
                state: val('jform_CarrierStateCode'),
                zip_code: val('jform_Zip'),
                dob_month: val('jform_Month'),
                dob_day: val('jform_Date'),
                dob_year: val('jform_Year'),
                experience: selText('jform_RequiredMinimumDrivingExperience'),
                license_types: checked('jform[LicenseTypeBit][]'),
                driver_types: checked('jform[DriverTypeBit][]'),
                trailer_experience: checked('jform[FreightTypeBit][]'),
                moving_violations: selText('jform_RequiredMinimumMovingViolations'),
                preventable_accidents: selText('jform_RequiredMinimumPreventableAccidents'),
                hazmat: val('jform_HazmatEndorsement') === '1' ? 'Yes' : 'No',
                dwi_dui: val('jform_DWI') === '1' ? 'Yes' : 'No',
                source: 'CDLjobs.com'
            };
        }""")

        # Build location string
        parts = [candidate.get('city', ''), candidate.get('state', ''), candidate.get('zip_code', '')]
        candidate['location'] = ', '.join(p.strip() for p in parts if p.strip())

        # Check if "Team" is in driver types
        candidate['wants_team'] = 'Team' in candidate.get('driver_types', [])

        print(f"✓ {candidate['first_name']} {candidate['last_name']} | {candidate['email']} | Exp: {candidate['experience']}")
        return candidate

    def get_all_applications(self) -> List[Dict]:
        """Get all applications."""
        ids = self.get_application_ids()
        applications = []
        for i, app_id in enumerate(ids):
            print(f"  [{i+1}/{len(ids)}] ", end="")
            try:
                app = self.get_application(app_id)
                applications.append(app)
            except Exception as e:
                print(f"  Error on ID {app_id}: {e}")
        return applications

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("Browser closed")


def main():
    """Extract all applications from CDLjobs"""
    import json

    scraper = CDLJobsScraper(headless=True)
    try:
        scraper.start()
        scraper.login()

        # Get all applications
        apps = scraper.get_all_applications()

        # Summary
        print("\n" + "=" * 60)
        print(f"TOTAL EXTRACTED: {len(apps)} applications")
        print("=" * 60)
        for app in apps:
            team = "TEAM" if app['wants_team'] else "solo"
            print(f"  {app['first_name']:15} {app['last_name']:15} | {app['experience']:20} | {team:5} | {app['location']}")

        # Save to JSON
        output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cdljobs_export.json")
        with open(output_path, 'w') as f:
            json.dump(apps, f, indent=2)
        print(f"\n✓ Saved to {output_path}")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
