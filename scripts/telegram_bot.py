"""
Telegram Bot for Divine Recruiting
Notifies Sergey about qualified candidates and collects his feedback.

Usage:
    python telegram_bot.py          # Run the bot (long-polling)
    python telegram_bot.py --test   # Send a test message
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from supabase import create_client

# ─── Config ──────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN", "8003820485:AAF7Oaj2tr1tm0s_uHbzDRuLJhLpvrV1bBA"
)
SERGEY_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "-5036058686"))

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

POLL_INTERVAL_SECONDS = 30

# ─── Supabase client ─────────────────────────────────────────────────────────

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ─── State: track which candidate we're collecting feedback for ───────────────

# Maps chat_id -> candidate_id for free-text replies
pending_feedback: dict[int, int] = {}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_candidate_message(c: dict) -> str:
    """Format candidate info for Telegram notification."""
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
        f"<a href='tg://user?id=1496678108'>Sergey</a>\n"
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


def candidate_keyboard(candidate_id: int) -> InlineKeyboardMarkup:
    """Inline buttons for quick feedback."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Hired", callback_data=f"hired:{candidate_id}"),
            InlineKeyboardButton("❌ Not Qualified", callback_data=f"notqual:{candidate_id}"),
        ],
        [
            InlineKeyboardButton("📝 Add Comment", callback_data=f"comment:{candidate_id}"),
        ],
    ])


# ─── Bot handlers ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Divine Recruiting Bot\n\n"
        "I'll notify you when candidates are qualified and need your review.\n\n"
        "Commands:\n"
        "/pending — show candidates awaiting your feedback\n"
        "/stats — recruiting statistics"
    )


async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show candidates awaiting Sergey's feedback."""
    result = (
        sb.table("candidates")
        .select("id, first_name, last_name, phone, notified_at")
        .eq("status", "Qualified / Awaiting Feedback")
        .not_.is_("notified_at", "null")
        .is_("feedback_at", "null")
        .execute()
    )
    candidates = result.data
    if not candidates:
        await update.message.reply_text("No candidates awaiting your feedback right now.")
        return

    lines = ["<b>Candidates awaiting your feedback:</b>\n"]
    for c in candidates:
        name = f"{c['first_name']} {c['last_name']}".strip()
        lines.append(f"• {name} — {c['phone']}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show recruiting statistics."""
    result = sb.table("candidates").select("status").execute()
    all_candidates = result.data

    total = len(all_candidates)
    counts = {}
    for c in all_candidates:
        s = c["status"]
        counts[s] = counts.get(s, 0) + 1

    text = (
        f"📊 <b>Recruiting Stats</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total candidates: <b>{total}</b>\n"
        f"New: {counts.get('New', 0)}\n"
        f"No Answer: {counts.get('No Answer', 0)}\n"
        f"Not Qualified: {counts.get('Not Qualified', 0)}\n"
        f"Awaiting Feedback: {counts.get('Qualified / Awaiting Feedback', 0)}\n"
        f"Hired by Us: {counts.get('Hired by Us', 0)}\n"
        f"Hired by Another: {counts.get('Hired by Another Company', 0)}\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, cid_str = data.split(":", 1)
    candidate_id = int(cid_str)

    now = datetime.now(timezone.utc).isoformat()

    # Fetch existing comment so we don't overwrite free-text feedback
    existing = sb.table("candidates").select("sergey_comment").eq("id", candidate_id).execute()
    prev_comment = (existing.data[0]["sergey_comment"] or "") if existing.data else ""

    if action == "hired":
        comment = f"{prev_comment}\nHired".strip() if prev_comment else "Hired"
        sb.table("candidates").update({
            "status": "Hired by Us",
            "feedback_at": now,
            "sergey_comment": comment,
        }).eq("id", candidate_id).execute()

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Marked as <b>Hired</b>!", parse_mode="HTML")
        log.info(f"Candidate {candidate_id} marked as Hired by Sergey")

    elif action == "notqual":
        comment = f"{prev_comment}\nNot Qualified".strip() if prev_comment else "Not Qualified — per Sergey"
        sb.table("candidates").update({
            "status": "Not Qualified",
            "feedback_at": now,
            "sergey_comment": comment,
        }).eq("id", candidate_id).execute()

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ Marked as <b>Not Qualified</b>", parse_mode="HTML")
        log.info(f"Candidate {candidate_id} marked as Not Qualified by Sergey")

    elif action == "comment":
        pending_feedback[query.message.chat_id] = candidate_id
        await query.message.reply_text(
            f"📝 Type your comment for this candidate (ID {candidate_id}):"
        )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages (comments from Sergey)."""
    chat_id = update.message.chat_id
    if chat_id not in pending_feedback:
        await update.message.reply_text(
            "I'm not expecting a comment right now. "
            "Use the buttons on a candidate notification to provide feedback."
        )
        return

    candidate_id = pending_feedback.pop(chat_id)
    comment = update.message.text.strip()
    now = datetime.now(timezone.utc).isoformat()

    sb.table("candidates").update({
        "feedback_at": now,
        "sergey_comment": comment,
    }).eq("id", candidate_id).execute()

    await update.message.reply_text(
        f"💾 Comment saved for candidate #{candidate_id}:\n<i>{comment}</i>",
        parse_mode="HTML",
    )
    log.info(f"Comment saved for candidate {candidate_id}: {comment}")


# ─── Polling job: check for new qualified candidates ──────────────────────────

async def check_new_qualified(ctx: ContextTypes.DEFAULT_TYPE):
    """Periodic job: find candidates with status 'Qualified / Awaiting Feedback'
    that haven't been notified yet, send Telegram message, set notified_at."""

    result = (
        sb.table("candidates")
        .select("*")
        .eq("status", "Qualified / Awaiting Feedback")
        .is_("notified_at", "null")
        .execute()
    )
    candidates = result.data

    for c in candidates:
        try:
            msg = format_candidate_message(c)
            keyboard = candidate_keyboard(c["id"])

            await ctx.bot.send_message(
                chat_id=SERGEY_CHAT_ID,
                text=msg,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

            # Mark as notified
            now = datetime.now(timezone.utc).isoformat()
            sb.table("candidates").update({
                "notified_at": now,
            }).eq("id", c["id"]).execute()

            name = f"{c['first_name']} {c['last_name']}".strip()
            log.info(f"Notified Sergey about candidate: {name} (ID {c['id']})")

        except Exception as e:
            log.error(f"Failed to notify about candidate {c['id']}: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Free text (comments)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Periodic job: check for new qualified candidates every N seconds
    app.job_queue.run_repeating(
        check_new_qualified,
        interval=POLL_INTERVAL_SECONDS,
        first=5,  # first check 5 seconds after start
    )

    log.info("Bot started. Polling for updates...")
    app.run_polling(drop_pending_updates=True)


async def send_test():
    """Send a test message to verify the bot works."""
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=SERGEY_CHAT_ID,
        text=(
            "🤖 <b>Divine Recruiting Bot</b> — Test Message\n\n"
            "Bot is connected and working!\n"
            "You'll receive notifications here when candidates are qualified."
        ),
        parse_mode="HTML",
    )
    print("✅ Test message sent!")


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(send_test())
    else:
        main()
