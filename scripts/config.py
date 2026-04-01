"""
Configuration for Divine Recruiting Automation
Fill in your credentials after receiving them from Divine
"""

import os

# =============================================================================
# EMAIL CONFIGURATION (IMAP/SMTP)
# =============================================================================
# Gmail for notifications (will switch to Divine email later)
EMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "nguzen@gmail.com")
EMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# =============================================================================
# CAREERPLUG CREDENTIALS
# =============================================================================
CAREERPLUG_URL = "https://app.careerplug.com"
CAREERPLUG_EMAIL = os.environ.get("CAREERPLUG_EMAIL", "nguzen@gmail.com")
CAREERPLUG_PASSWORD = os.environ.get("CAREERPLUG_PASSWORD", "")

# =============================================================================
# DIVINE ENTERPRISES INFO
# =============================================================================
INTELLIAPP_URL = "https://intelliapp.driverapponline.com/c/divinetrans"
COMPANY_PHONE = "(916) 781-7200 ext. 214"
COMPANY_NAME = "Divine Enterprises"

# =============================================================================
# SENDER INFO (for outgoing emails)
# =============================================================================
SENDER_NAME = "Nikita Guzenko"
SENDER_PHONE = "(305) 413-8988"

# =============================================================================
# DIVINE CORPORATE EMAIL (fill when received)
# =============================================================================
# When you get corporate email, fill these and set USE_DIVINE_EMAIL = True
USE_DIVINE_EMAIL = False
DIVINE_EMAIL = ""  # e.g., nikita@divinetrans.com
DIVINE_EMAIL_PASSWORD = ""
DIVINE_IMAP_SERVER = ""  # e.g., mail.divinetrans.com
DIVINE_SMTP_SERVER = ""  # e.g., mail.divinetrans.com

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
CANDIDATES_CSV = os.path.join(DATA_DIR, "candidates.csv")
EMAIL_TEMPLATE = os.path.join(TEMPLATES_DIR, "candidate_email.md")
PRESCREENING_TEMPLATE = os.path.join(TEMPLATES_DIR, "prescreening_email.md")

# =============================================================================
# QUO (OPENPHONE) API
# =============================================================================
QUO_API_KEY = os.environ.get("QUO_API_KEY", "")
QUO_API_BASE = "https://api.openphone.com/v1"
QUO_PHONE_NUMBER_ID = "PN49arHHea"  # (916) 249-0761

# =============================================================================
# AUTOMATION SETTINGS
# =============================================================================
CHECK_INTERVAL_MINUTES = 15  # How often to check for new candidates
HEADLESS_BROWSER = False     # Set True to run browser in background

# =============================================================================
# PATHS - CALLS
# =============================================================================
CALLS_DIR = os.path.join(DATA_DIR, "calls")
CALLS_RECORDINGS_DIR = os.path.join(CALLS_DIR, "recordings")
