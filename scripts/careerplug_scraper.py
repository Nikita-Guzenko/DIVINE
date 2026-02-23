"""
CareerPlug Candidate Scraper
Extracts candidate data from CareerPlug using Playwright
"""

import re
from datetime import datetime
from playwright.sync_api import sync_playwright
import config


# CareerPlug CDL-A job ID
CDL_JOB_ID = "3270521"


class CareerPlugScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self.logged_in = False

    def start(self):
        """Initialize browser"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        print("Browser started")

    def login(self):
        """Login to CareerPlug (two-step form)"""
        if not config.CAREERPLUG_EMAIL or not config.CAREERPLUG_PASSWORD:
            raise ValueError("CareerPlug credentials not configured in config.py")

        print("Logging into CareerPlug...")
        self.page.goto(f"{config.CAREERPLUG_URL}/user/sign_in",
                       wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(2000)

        # Step 1: Enter email
        self.page.fill('#user_login', config.CAREERPLUG_EMAIL)
        self.page.click('#user_continue_action')
        self.page.wait_for_timeout(2000)

        # Step 2: Enter password
        self.page.fill('#user_password', config.CAREERPLUG_PASSWORD)
        self.page.click('#user_submit_action')
        self.page.wait_for_timeout(3000)

        if "sign_in" not in self.page.url:
            self.logged_in = True
            print("✓ Logged into CareerPlug")
        else:
            raise Exception("Failed to login to CareerPlug")

    def get_applicant_ids(self, status: str = "all") -> list:
        """Get all applicant IDs from the list page.
        status: 'all', 'active', 'new', 'disqualified', 'hired'
        """
        if not self.logged_in:
            self.login()

        # Navigate to applicants list filtered by CDL-A job
        url = (f"{config.CAREERPLUG_URL}/manage/apps"
               f"?status={status}&apps_j[]={CDL_JOB_ID}&per_page=100")
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(3000)

        all_ids = []
        page = 1

        while True:
            # Extract app IDs from links
            ids = self.page.eval_on_selector_all(
                'a[href*="/manage/apps/"]',
                """elements => {
                    const seen = new Set();
                    return elements
                        .map(a => {
                            const match = a.href.match(/\\/apps\\/(\\d+)/);
                            return match ? match[1] : null;
                        })
                        .filter(id => {
                            if (!id || seen.has(id)) return false;
                            seen.add(id);
                            return true;
                        });
                }"""
            )

            if not ids:
                break

            all_ids.extend(ids)

            # Check for next page
            next_btn = self.page.query_selector('a[rel="next"], .next a')
            if next_btn:
                page += 1
                next_btn.click()
                self.page.wait_for_timeout(3000)
            else:
                break

        print(f"✓ Found {len(all_ids)} applicants ({page} pages)")
        return all_ids

    def get_applicant(self, app_id: str) -> dict:
        """Extract all data from a single applicant profile."""
        if not self.logged_in:
            self.login()

        url = f"{config.CAREERPLUG_URL}/manage/apps/{app_id}"
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(2000)

        # Extract structured header data
        header_data = self.page.evaluate("""() => {
            const body = document.body.innerText;
            const data = {};

            // Email
            const emailEl = document.querySelector('a[href^="mailto:"]');
            data.email = emailEl ? emailEl.textContent.trim() : '';

            // Phone
            const phoneEl = document.querySelector('a[href^="tel:"]');
            data.phone = phoneEl ? phoneEl.textContent.trim().replace(/^1/, '') : '';

            // Applied for
            const posMatch = body.match(/Applied for:\\s*([^\\n]+)/);
            data.position = posMatch ? posMatch[1].trim() : '';

            // Source
            const srcMatch = body.match(/via\\s+(.+?)$/m);
            data.source = srcMatch ? 'CareerPlug/' + srcMatch[1].trim() : 'CareerPlug';

            // Date
            const dateMatch = body.match(/Applied on\\s+(\\S+)/);
            data.applied_date = dateMatch ? dateMatch[1].trim() : '';

            // Name - appears after position line
            const nameMatch = body.match(/Rocklin\\n(.+?)\\n/);
            if (!nameMatch) {
                // Try alternative: name is between job title line and "Next Steps"
                const altMatch = body.match(/CPM[^\\n]*\\n([A-Za-z\\s]+?)\\n/);
                data.full_name = altMatch ? altMatch[1].trim() : '';
            } else {
                data.full_name = nameMatch[1].trim();
            }

            return data;
        }""")

        # Extract resume text
        resume_text = self.page.evaluate("""() => {
            const el = document.querySelector('.resume-container');
            return el ? el.innerText.trim() : '';
        }""")

        # Parse name
        full_name = header_data.get('full_name', '')
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Parse location from resume (usually near top: "City, ST ZIP")
        location = ''
        # Search line by line for "City, ST ZIP" pattern
        for line in resume_text[:500].split('\n'):
            line = line.strip()
            loc_match = re.match(r'^([A-Za-z\s]{2,30}),\s*([A-Z]{2})\s*(\d{5})?$', line)
            if loc_match:
                city = loc_match.group(1).strip()
                state = loc_match.group(2)
                zipcode = loc_match.group(3) or ''
                location = f"{city}, {state} {zipcode}".strip()
                break

        # Parse endorsements from resume
        endorsements = []
        resume_lower = resume_text.lower()
        if 'hazmat' in resume_lower:
            endorsements.append('Hazmat')
        if 'tanker' in resume_lower:
            endorsements.append('Tanker')
        if 'double' in resume_lower or 'triple' in resume_lower:
            endorsements.append('Doubles/Triples')

        # Parse license type
        license_types = []
        if 'class a' in resume_lower:
            license_types.append('Class A')
        if 'class b' in resume_lower:
            license_types.append('Class B')

        # Parse experience keywords
        trailer_experience = []
        for keyword in ['reefer', 'refrigerat', 'flatbed', 'dry van', 'tanker', 'hazmat']:
            if keyword in resume_lower:
                label = {
                    'reefer': 'Reefer', 'refrigerat': 'Reefer',
                    'flatbed': 'Flatbed', 'dry van': 'Dry Van',
                    'tanker': 'Tanker', 'hazmat': 'Hazmat'
                }.get(keyword, keyword)
                if label not in trailer_experience:
                    trailer_experience.append(label)

        candidate = {
            'careerplug_id': app_id,
            'first_name': first_name.title(),
            'last_name': last_name.title(),
            'email': header_data.get('email', ''),
            'phone': header_data.get('phone', ''),
            'location': location,
            'position': header_data.get('position', ''),
            'source': header_data.get('source', 'CareerPlug'),
            'applied_date': header_data.get('applied_date', ''),
            'license_types': license_types,
            'endorsements': endorsements,
            'trailer_experience': trailer_experience,
            'resume_text': resume_text[:3000],
            'careerplug_url': self.page.url,
        }

        print(f"✓ {candidate['first_name']} {candidate['last_name']} | {candidate['email']} | {candidate['source']}")
        return candidate

    def get_all_applicants(self, status: str = "all") -> list:
        """Get all applicants with full data."""
        ids = self.get_applicant_ids(status=status)
        applicants = []
        for i, app_id in enumerate(ids):
            print(f"  [{i+1}/{len(ids)}] ", end="")
            try:
                app = self.get_applicant(app_id)
                applicants.append(app)
            except Exception as e:
                print(f"  Error on ID {app_id}: {e}")
        return applicants

    def close(self):
        """Close browser"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("Browser closed")


def main():
    """Extract all CDL-A applicants from CareerPlug"""
    import json
    import os

    scraper = CareerPlugScraper(headless=True)
    try:
        scraper.start()
        scraper.login()

        # Get all active CDL-A applicants
        apps = scraper.get_all_applicants(status="all")

        # Summary
        print("\n" + "=" * 60)
        print(f"TOTAL EXTRACTED: {len(apps)} applicants")
        print("=" * 60)
        for app in apps:
            endorse = ', '.join(app['endorsements']) if app['endorsements'] else 'none'
            print(f"  {app['first_name']:15} {app['last_name']:15} | {app['location']:25} | Endorse: {endorse}")

        # Save to JSON
        output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "careerplug_export.json")
        with open(output_path, 'w') as f:
            json.dump(apps, f, indent=2)
        print(f"\n✓ Saved to {output_path}")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
