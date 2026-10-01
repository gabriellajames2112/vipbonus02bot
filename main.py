import logging
import os
import sqlite3
import html
from datetime import datetime, timedelta, time, timezone
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.error import NetworkError, TimedOut, Forbidden

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")
DB_PATH = os.getenv("DB_PATH", "subscribers.db")

# --- YOUR EVENT DATA ---
EVENTS = [
    {
        "title": "Detty December Fest: Wizkid Live",
        "date": "2026-12-18",
        "type": "Concert",
        "venue": "Ilubirin, Lagos",
        "link": "https://www.dettydecfest.com"
    },
    {
        "title": "NAFEST 2026: Culture Olympics",
        "date": "2026-11-21",
        "type": "Cultural Festival",
        "venue": "Enugu",
        "link": "https://guardian.ng/art/nafest-returns-to-enugu-with-new-competitions-gaming-concerts/"
    },
    {
        "title": "The Lion King: Theater Production",
        "date": "2026-10-15",
        "type": "Theater",
        "venue": "National Theatre, Lagos",
        "link": "https://www.example.com"
    }
]

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- DATABASE (SQLite, no external service needed) ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id INTEGER PRIMARY KEY,
            joined_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_subscriber(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO subscribers (chat_id, joined_at) VALUES (?, ?)",
        (chat_id, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

def remove_subscriber(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def get_subscribers():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
    conn.close()
    return [r[0] for r in rows]

# --- HELPER FUNCTIONS ---

def get_upcoming_events(days_ahead=30, category=None):
    today = datetime.now().date()
    end_date = today + timedelta(days=days_ahead)
    upcoming = []
    for event in EVENTS:
        try:
            event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
            if today <= event_date <= end_date:
                if category and event["type"].lower() != category.lower():
                    continue
                upcoming.append(event)
        except ValueError:
            continue
    upcoming.sort(key=lambda x: x["date"])
    return upcoming

def format_event(event):
    return (
        f"🎭 <b>{html.escape(event['title'])}</b>\n"
        f"📅 <b>Date:</b> {event['date']}\n"
        f"📍 <b>Venue:</b> {html.escape(event['venue'])}\n"
        f"🏷 <b>Type:</b> {html.escape(event['type'])}\n"
        f"🔗 <a href='{event['link']}'>More Info</a>"
    )

async def send_events_to_chat(bot, chat_id: int, events: list):
    """Sends a list of events to a single chat, handling blocked users."""
    for event in events:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=format_event(event),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Forbidden:
            # User blocked the bot — remove them
            logger.info(f"User {chat_id} blocked the bot. Removing subscriber.")
            remove_subscriber(chat_id)
            return False
        except (NetworkError, TimedOut) as e:
            logger.warning(f"Network issue sending to {chat_id}: {e}")
            return False
    return True

# --- BOT COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    add_subscriber(chat_id)

    await update.message.reply_html(
        f"Hi {user.mention_html()}! 👋\n\n"
        f"Welcome to the <b>Cultural Events Calendar</b>.\n"
        f"You're now subscribed and will receive upcoming concerts, movies, "
        f"theater, and cultural events automatically.\n\n"
        f"<b>Commands:</b>\n"
        f"/events – View upcoming events\n"
        f"/concerts – Filter concerts\n"
        f"/movies – Filter movies\n"
        f"/theater – Filter theater\n"
        f"/festivals – Filter festivals\n"
        f"/stop – Unsubscribe"
    )
    await send_event_list(update, context)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    remove_subscriber(chat_id)
    await update.message.reply_text("You've been unsubscribed. Send /start anytime to rejoin.")

async def send_event_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    events = get_upcoming_events(days_ahead=30)
    if not events:
        await update.message.reply_text("No upcoming events in the next 30 days. Check back later!")
        return
    for event in events:
        await update.message.reply_html(format_event(event), disable_web_page_preview=True)

async def filter_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /concerts, /movies, /theater, /festivals."""
    command = update.message.text.split()[0].lstrip("/").lower()
    mapping = {
        "concerts": "Concert",
        "movies": "Movie",
        "theater": "Theater",
        "festivals": "Cultural Festival",
    }
    category = mapping.get(command)
    events = get_upcoming_events(days_ahead=90, category=category)
    if not events:
        await update.message.reply_text(f"No upcoming {command} found.")
        return
    for event in events:
        await update.message.reply_html(format_event(event), disable_web_page_preview=True)

# --- SCHEDULED BROADCAST ---

async def send_weekly_updates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast to all subscribers + optional channel every week."""
    events = get_upcoming_events(days_ahead=7)
    if not events:
        logger.info("No events this week. Skipping broadcast.")
        return

    header = "🗓 <b>This Week in Culture</b>\n\nHere's what's coming up:\n\n"
    subscribers = get_subscribers()
    logger.info(f"Broadcasting to {len(subscribers)} subscribers.")

    for chat_id in subscribers:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=header,
                parse_mode="HTML"
            )
            await send_events_to_chat(context.bot, chat_id, events)
        except Exception as e:
            logger.error(f"Broadcast error for {chat_id}: {e}")

    # Optional: also post to a channel
    channel_id = os.getenv("TARGET_CHANNEL_ID")
    if channel_id:
        try:
            await context.bot.send_message(
                chat_id=channel_id,
                text=header,
                parse_mode="HTML"
            )
            await send_events_to_chat(context.bot, int(channel_id), events)
        except Exception as e:
            logger.error(f"Channel broadcast error: {e}")

# --- ERROR HANDLER ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors cleanly. Ignore transient network errors."""
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        logger.warning(f"Transient network error (will retry): {err}")
        return
    logger.error(f"Update {update} caused error: {err}", exc_info=err)

# --- MAIN ---

def main() -> None:
    if TOKEN == "YOUR_TOKEN_HERE":
        logger.error("Please set TELEGRAM_BOT_TOKEN environment variable!")
        return

    init_db()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("events", send_event_list))
    application.add_handler(CommandHandler("concerts", filter_events))
    application.add_handler(CommandHandler("movies", filter_events))
    application.add_handler(CommandHandler("theater", filter_events))
    application.add_handler(CommandHandler("festivals", filter_events))

    # Register the error handler — this is the KEY fix for your log spam
    application.add_error_handler(error_handler)

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_daily(
            send_weekly_updates,
            time=time(hour=10, minute=0, tzinfo=timezone.utc),
            days=(0,),  # Monday (0=Mon in PTB's JobQueue)
        )
        logger.info("Weekly broadcast scheduled for Mondays at 10:00 UTC.")

    logger.info("Bot starting...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
