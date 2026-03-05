"""
Bot Cron Worker — runs every 15 minutes via GitHub Actions.
1. Checks for unnotified qualified candidates → sends Telegram messages
2. Processes pending Telegram button presses (Hired / Not Qualified / Comment)
"""

import os
import sys
import re
import json
import httpx
from datetime import datetime, timezone

from supabase import create_client

# ─── Config ──────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN", "8003820485:AAF7Oaj2tr1tm0s_uHbzDRuLJhLpvrV1bBA"
)
TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "-5036058686"))
SERGEY_USER_ID = 1496678108

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://psrsosfjteeovtmszwgu.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzcnNvc2ZqdGVlb3Z0bXN6d2d1Iiwi"
    "cm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTUzMjYwMCwiZXhwIjoyMDg3"
    "MTA4NjAwfQ.X5YF9ZlzmKtlRRK_P1AxWdZfijKCMijEAAXuK76vlME"
)

API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─── Telegram helpers ────────────────────────────────────────────────────────

def tg_request(method: str, data: dict) -> dict:
    r = httpx.post(f"{API}/{method}", json=data, timeout=30)
    return r.json()


def format_candidate(c: dict) -> str:
    name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
    phone = c.get("phone", "—")
    location = c.get("location", "—")
    experience = c.get("experience", "—")
    license_types = ", ".join(c.get("license_types") or []) or "—"
    endorsements = ", ".join(c.get("endorsements") or []) or "None"
    trailer = ", ".join(c.get("trailer_experience") or []) or "—"
    violations = c.get("moving_violations", "—")
    accidents = c.get("preventable_accidents", "—")
    dui = c.get("dwi_dui", "—")

    return (
        f"<a href='tg://user?id={SERGEY_USER_ID}'>Sergey</a>\n"
        f"🚛 <b>New Candidate</b>\n\n"
        f"<b>Name:</b> {name}\n"
        f"<b>Phone:</b> {phone}\n"
        f"<b>Location:</b> {location}\n"
        f"<b>Experience:</b> {experience}\n"
        f"<b>License:</b> {license_types}\n"
        f"<b>Endorsements:</b> {endorsements}\n"
        f"<b>Trailer:</b> {trailer}\n"
        f"<b>Violations:</b> {violations} | <b>Accidents:</b> {accidents} | <b>DUI:</b> {dui}"
    )


def candidate_keyboard(candidate_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Hired", "callback_data": f"hired:{candidate_id}"},
                {"text": "❌ Not Qualified", "callback_data": f"notqual:{candidate_id}"},
            ],
            [
                {"text": "📝 Add Comment", "callback_data": f"comment:{candidate_id}"},
            ],
        ]
    }


# ─── Step 1: Send notifications for new qualified candidates ─────────────────

def send_notifications():
    result = (
        sb.table("candidates")
        .select("*")
        .eq("status", "Qualified / Awaiting Feedback")
        .is_("notified_at", "null")
        .execute()
    )
    candidates = result.data
    if not candidates:
        print("[BOT] No new candidates to notify about.")
        return 0

    sent = 0
    for c in candidates:
        msg = format_candidate(c)
        keyboard = candidate_keyboard(c["id"])

        resp = tg_request("sendMessage", {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        })

        if resp.get("ok"):
            now = datetime.now(timezone.utc).isoformat()
            sb.table("candidates").update({"notified_at": now}).eq("id", c["id"]).execute()
            name = f"{c['first_name']} {c['last_name']}".strip()
            print(f"[BOT] Notified about: {name} (ID {c['id']})")
            sent += 1
        else:
            print(f"[BOT] Failed to send for ID {c['id']}: {resp}")

    return sent


# ─── Step 2: Process pending Telegram updates (button presses) ───────────────

def process_updates():
    # Get pending updates (non-blocking)
    resp = tg_request("getUpdates", {"timeout": 0})
    if not resp.get("ok"):
        print(f"[BOT] getUpdates failed: {resp}")
        return

    updates = resp.get("result", [])
    if not updates:
        print("[BOT] No pending Telegram updates.")
        return

    processed = 0
    for update in updates:
        callback = update.get("callback_query")
        if not callback:
            continue

        data = callback.get("data", "")
        if ":" not in data:
            continue

        action, cid_str = data.split(":", 1)
        try:
            candidate_id = int(cid_str)
        except ValueError:
            continue

        now = datetime.now(timezone.utc).isoformat()
        callback_id = callback.get("id")

        # Fetch existing comment
        existing = sb.table("candidates").select("sergey_comment").eq("id", candidate_id).execute()
        prev_comment = (existing.data[0]["sergey_comment"] or "") if existing.data else ""

        if action == "hired":
            comment = f"{prev_comment}\nHired".strip() if prev_comment else "Hired"
            sb.table("candidates").update({
                "status": "Hired by Us",
                "feedback_at": now,
                "sergey_comment": comment,
            }).eq("id", candidate_id).execute()

            tg_request("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "Marked as Hired!",
            })

            # Remove buttons from message
            msg = callback.get("message", {})
            if msg.get("chat", {}).get("id") and msg.get("message_id"):
                tg_request("editMessageReplyMarkup", {
                    "chat_id": msg["chat"]["id"],
                    "message_id": msg["message_id"],
                    "reply_markup": {"inline_keyboard": []},
                })

            print(f"[BOT] Candidate {candidate_id} → Hired")
            processed += 1

        elif action == "notqual":
            comment = f"{prev_comment}\nNot Qualified".strip() if prev_comment else "Not Qualified — per Sergey"
            sb.table("candidates").update({
                "status": "Not Qualified",
                "feedback_at": now,
                "sergey_comment": comment,
            }).eq("id", candidate_id).execute()

            tg_request("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "Marked as Not Qualified",
            })

            msg = callback.get("message", {})
            if msg.get("chat", {}).get("id") and msg.get("message_id"):
                tg_request("editMessageReplyMarkup", {
                    "chat_id": msg["chat"]["id"],
                    "message_id": msg["message_id"],
                    "reply_markup": {"inline_keyboard": []},
                })

            print(f"[BOT] Candidate {candidate_id} → Not Qualified")
            processed += 1

        elif action == "comment":
            tg_request("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "Send your comment as a reply to the candidate message.",
            })

            msg = callback.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            message_id = msg.get("message_id")
            if chat_id and message_id:
                name_resp = sb.table("candidates").select("first_name, last_name").eq("id", candidate_id).execute()
                cname = ""
                if name_resp.data:
                    cname = f"{name_resp.data[0].get('first_name', '')} {name_resp.data[0].get('last_name', '')}".strip()
                tg_request("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"📝 Reply to this message with your comment for <b>{cname}</b> (ID {candidate_id}):",
                    "parse_mode": "HTML",
                    "reply_to_message_id": message_id,
                    "reply_markup": {"force_reply": True, "selective": True},
                })

            print(f"[BOT] Comment requested for candidate {candidate_id}")
            processed += 1

    # Process text messages (comment replies)
    for update in updates:
        message = update.get("message")
        if not message:
            continue
        text = message.get("text", "").strip()
        if not text:
            continue

        # Check if this is a reply to a comment prompt
        reply_to = message.get("reply_to_message")
        if not reply_to:
            continue
        reply_text = reply_to.get("text", "")
        if "Reply to this message with your comment" not in reply_text and "ID " not in reply_text:
            continue

        # Extract candidate ID from the prompt message
        id_match = re.search(r"ID (\d+)", reply_text)
        if not id_match:
            continue
        candidate_id = int(id_match.group(1))

        now = datetime.now(timezone.utc).isoformat()
        sb.table("candidates").update({
            "feedback_at": now,
            "sergey_comment": text,
        }).eq("id", candidate_id).execute()

        chat_id = message["chat"]["id"]
        tg_request("sendMessage", {
            "chat_id": chat_id,
            "text": f"💾 Comment saved for candidate #{candidate_id}:\n<i>{text}</i>",
            "parse_mode": "HTML",
        })

        from_user = message.get("from", {}).get("first_name", "Someone")
        print(f"[BOT] Comment from {from_user} saved for candidate {candidate_id}: {text}")
        processed += 1

    # Confirm all processed updates
    if updates:
        last_id = updates[-1]["update_id"]
        tg_request("getUpdates", {"offset": last_id + 1, "timeout": 0})

    print(f"[BOT] Processed {processed} button presses.")


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[BOT] Cron run at {datetime.now(timezone.utc).isoformat()}")
    sent = send_notifications()
    process_updates()
    print(f"[BOT] Done. Sent {sent} notifications.")
