"""
Auto Sync Pipeline — Automated Candidate Scraping
Runs both CareerPlug and CDLjobs scrapers, deduplicates against Supabase,
inserts new candidates, and sends a Telegram summary.

Designed to run every 4 hours via GitHub Actions.

Usage:
    python auto_sync.py                  # Run both scrapers
    python auto_sync.py --careerplug     # CareerPlug only
    python auto_sync.py --cdljobs        # CDLjobs only
    python auto_sync.py --dry-run        # Scrape but don't write
"""

import os
import re
import sys
import argparse
from datetime import datetime, timezone

import httpx
from supabase import create_client

# Add scripts dir to path so we can import scrapers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from careerplug_scraper import CareerPlugScraper
from cdljobs_scraper import CDLJobsScraper

# ─── Config ──────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://psrsosfjteeovtmszwgu.supabase.co"
)
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-5036058686")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def normalize_phone(phone: str) -> str:
    """Normalize phone for deduplication: strip formatting and leading 1."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", phone)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    return digits


def load_existing_contacts(sb):
    """Load all emails and phones from Supabase for O(1) dedup lookups."""
    result = sb.table("candidates").select("email, phone").execute()
    emails = set()
    phones = set()
    for r in result.data:
        if r.get("email"):
            emails.add(r["email"].strip().lower())
        if r.get("phone"):
            norm = normalize_phone(r["phone"])
            if norm:
                phones.add(norm)
    return emails, phones


def is_duplicate(email: str, phone: str, existing_emails: set, existing_phones: set) -> bool:
    """Check if candidate already exists by email or phone."""
    if email and email.strip().lower() in existing_emails:
        return True
    if phone and normalize_phone(phone) in existing_phones:
        return True
    return False


def map_careerplug_to_supabase(c: dict) -> dict:
    """Transform CareerPlug scraper output to Supabase row."""
    return {
        "first_name": c.get("first_name", ""),
        "last_name": c.get("last_name", ""),
        "email": c.get("email", "").strip().lower(),
        "phone": c.get("phone", ""),
        "location": c.get("location", ""),
        "source": c.get("source", "CareerPlug"),
        "source_url": c.get("careerplug_url", ""),
        "applied_date": c.get("applied_date", ""),
        "license_types": c.get("license_types", []),
        "endorsements": c.get("endorsements", []),
        "trailer_experience": c.get("trailer_experience", []),
        "resume_text": c.get("resume_text", ""),
        "status": "New",
    }


def map_cdljobs_to_supabase(c: dict) -> dict:
    """Transform CDLjobs scraper output to Supabase row."""
    endorsements = []
    if c.get("hazmat") == "Yes":
        endorsements.append("Hazmat")

    return {
        "first_name": c.get("first_name", ""),
        "last_name": c.get("last_name", ""),
        "email": c.get("email", "").strip().lower(),
        "phone": c.get("phone", ""),
        "address": c.get("address", ""),
        "city": c.get("city", ""),
        "state": c.get("state", ""),
        "zip_code": c.get("zip_code", ""),
        "location": c.get("location", ""),
        "source": "CDLjobs.com",
        "experience": c.get("experience", ""),
        "license_types": c.get("license_types", []),
        "driver_types": c.get("driver_types", []),
        "trailer_experience": c.get("trailer_experience", []),
        "endorsements": endorsements,
        "wants_team": c.get("wants_team", False),
        "moving_violations": c.get("moving_violations", ""),
        "preventable_accidents": c.get("preventable_accidents", ""),
        "hazmat": c.get("hazmat", ""),
        "dwi_dui": c.get("dwi_dui", ""),
        "status": "New",
    }


def insert_to_supabase(sb, candidate: dict) -> bool:
    """Insert a single candidate to Supabase."""
    try:
        result = sb.table("candidates").insert(candidate).execute()
        return bool(result.data)
    except Exception as e:
        print(f"  [ERROR] Supabase insert failed: {e}")
        return False


def send_telegram(message: str):
    """Send summary message to Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        print("[WARN] No TELEGRAM_BOT_TOKEN, skipping notification")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
    except Exception as e:
        print(f"[WARN] Telegram notification failed: {e}")


# ─── Main Pipeline ───────────────────────────────────────────────────────────

def run_pipeline(run_careerplug=True, run_cdljobs=True, dry_run=False):
    """Run the full scraping and sync pipeline."""
    print("=" * 60)
    print(f"DIVINE Auto Sync — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Sources: {'CareerPlug' if run_careerplug else ''} {'CDLjobs' if run_cdljobs else ''}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    # Connect to Supabase
    if not SUPABASE_KEY:
        print("[ERROR] SUPABASE_KEY not set")
        send_telegram("❌ <b>Auto Sync Failed</b>\nSUPABASE_KEY not configured")
        return
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Load existing contacts for dedup
    print("\nLoading existing candidates for deduplication...")
    existing_emails, existing_phones = load_existing_contacts(sb)
    print(f"  {len(existing_emails)} emails, {len(existing_phones)} phones in database")

    results = {
        "careerplug_scraped": 0,
        "cdljobs_scraped": 0,
        "new_added": 0,
        "duplicates": 0,
        "errors": [],
        "new_candidates": [],
    }

    # ── CareerPlug ───────────────────────────────────────────────
    if run_careerplug:
        print("\n── CareerPlug ──────────────────────────────────")
        scraper = CareerPlugScraper(headless=True)
        try:
            scraper.start()
            scraper.login()
            candidates = scraper.get_all_applicants(status="new")
            results["careerplug_scraped"] = len(candidates)
            print(f"  Scraped {len(candidates)} candidates")

            for c in candidates:
                name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                if is_duplicate(c.get("email", ""), c.get("phone", ""), existing_emails, existing_phones):
                    print(f"  [SKIP] {name} — duplicate")
                    results["duplicates"] += 1
                    continue

                mapped = map_careerplug_to_supabase(c)
                if not dry_run:
                    if insert_to_supabase(sb, mapped):
                        print(f"  [NEW] {name} — added to Supabase")
                        # Add to existing set to prevent intra-batch duplicates
                        if mapped["email"]:
                            existing_emails.add(mapped["email"])
                        if mapped["phone"]:
                            existing_phones.add(normalize_phone(mapped["phone"]))
                    else:
                        results["errors"].append(f"CareerPlug insert failed: {name}")
                        continue
                else:
                    print(f"  [DRY] {name} — would be added")

                results["new_added"] += 1
                results["new_candidates"].append(name)

        except Exception as e:
            err = f"CareerPlug scraper error: {e}"
            print(f"  [ERROR] {err}")
            results["errors"].append(err)
        finally:
            scraper.close()

    # ── CDLjobs ──────────────────────────────────────────────────
    if run_cdljobs:
        print("\n── CDLjobs ────────────────────────────────────")
        scraper = CDLJobsScraper(headless=True)
        try:
            scraper.start()
            scraper.login()
            candidates = scraper.get_all_applications()
            results["cdljobs_scraped"] = len(candidates)
            print(f"  Scraped {len(candidates)} candidates")

            for c in candidates:
                name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                if is_duplicate(c.get("email", ""), c.get("phone", ""), existing_emails, existing_phones):
                    print(f"  [SKIP] {name} — duplicate")
                    results["duplicates"] += 1
                    continue

                mapped = map_cdljobs_to_supabase(c)
                if not dry_run:
                    if insert_to_supabase(sb, mapped):
                        print(f"  [NEW] {name} — added to Supabase")
                        if mapped["email"]:
                            existing_emails.add(mapped["email"])
                        if mapped["phone"]:
                            existing_phones.add(normalize_phone(mapped["phone"]))
                    else:
                        results["errors"].append(f"CDLjobs insert failed: {name}")
                        continue
                else:
                    print(f"  [DRY] {name} — would be added")

                results["new_added"] += 1
                results["new_candidates"].append(name)

        except Exception as e:
            err = f"CDLjobs scraper error: {e}"
            print(f"  [ERROR] {err}")
            results["errors"].append(err)
        finally:
            scraper.close()

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_scraped = results["careerplug_scraped"] + results["cdljobs_scraped"]
    print(f"  Scraped:    {total_scraped} (CareerPlug: {results['careerplug_scraped']}, CDLjobs: {results['cdljobs_scraped']})")
    print(f"  New added:  {results['new_added']}")
    print(f"  Duplicates: {results['duplicates']}")
    if results["errors"]:
        print(f"  Errors:     {len(results['errors'])}")
        for err in results["errors"]:
            print(f"    - {err}")

    # ── Telegram notification ────────────────────────────────────
    if not dry_run:
        if results["new_added"] > 0:
            names_list = "\n".join(f"• {n}" for n in results["new_candidates"])
            msg = (
                f"🚛 <b>Auto Sync Complete</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>New candidates:</b> {results['new_added']}\n"
                f"{names_list}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Scraped: {total_scraped} | Duplicates: {results['duplicates']}"
            )
            send_telegram(msg)
        elif results["errors"]:
            errors_text = "\n".join(f"• {e}" for e in results["errors"])
            send_telegram(
                f"⚠️ <b>Auto Sync Errors</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"{errors_text}\n"
                f"Scraped: {total_scraped} | No new candidates"
            )
        # No notification if everything is fine but no new candidates (quiet success)

    return results


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DIVINE Auto Sync Pipeline")
    parser.add_argument("--careerplug", action="store_true", help="Run CareerPlug only")
    parser.add_argument("--cdljobs", action="store_true", help="Run CDLjobs only")
    parser.add_argument("--dry-run", action="store_true", help="Scrape without writing")
    args = parser.parse_args()

    # If neither specified, run both
    run_cp = args.careerplug or (not args.careerplug and not args.cdljobs)
    run_cdl = args.cdljobs or (not args.careerplug and not args.cdljobs)

    run_pipeline(run_careerplug=run_cp, run_cdljobs=run_cdl, dry_run=args.dry_run)
