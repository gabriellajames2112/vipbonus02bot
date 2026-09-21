import logging
import os
from datetime import datetime, timedelta, time, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")

# --- YOUR EVENT DATA ---
# Add new events here. Format: YYYY-MM-DD
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
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---

def get_upcoming_events(days_ahead=30):
    """Filters the EVENTS list for events happening in the next X days."""
    today = datetime.now().date()
    end_date = today + timedelta(days=days_ahead)

    upcoming = []
    for event in EVENTS:
        try:
            event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
            if today <= event_date <= end_date:
                upcoming.append(event)
        except ValueError:
            continue

    upcoming.sort(key=lambda x: x["date"])
    return upcoming

def format_event(event):
    """Formats an event dictionary into a nice Telegram message."""
    return (
        f"🎭 <b>{event['title']}</b>\n"
        f"📅 <b>Date:</b> {event['date']}\n"
        f"📍 <b>Venue:</b> {event['venue']}\n"
        f"🏷 <b>Type:</b> {event['type']}\n"
        f"🔗 <a href='{event['link']}'>More Info</a>"
    )

# --- BOT COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and instantly sends upcoming events."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! 👋\n\n"
        f"Welcome to the <b>Cultural Events Calendar</b>.\n"
        f"I'll send you upcoming concerts, movies, theater, and more.\n\n"
        f"Here are the events happening in the next 30 days:"
    )
    await send_event_list(update, context)

async def send_event_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the current list of upcoming events."""
    events = get_upcoming_events(days_ahead=30)

    if not events:
        await update.message.reply_text("No upcoming events found for the next 30 days. Check back later!")
        return

    for event in events:
        await update.message.reply_html(format_event(event), disable_web_page_preview=True)

# --- SCHEDULED JOB ---

async def send_weekly_updates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcasts upcoming events to a target channel every Monday."""
    target_chat_id = os.getenv("TARGET_CHANNEL_ID")

    if not target_chat_id:
        logger.info("No TARGET_CHANNEL_ID set. Skipping weekly broadcast.")
        return

    events = get_upcoming_events(days_ahead=7)

    if not events:
        return

    message = "🗓 <b>This Week in Culture</b>\n\nHere are the upcoming events:\n\n"
    for event in events:
        message += format_event(event) + "\n\n"

    try:
        await context.bot.send_message(
            chat_id=target_chat_id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        logger.info(f"Weekly update sent to {target_chat_id}")
    except Exception as e:
        logger.error(f"Failed to send weekly update: {e}")

# --- MAIN ---

def main() -> None:
    """Start the bot."""
    if TOKEN == "YOUR_TOKEN_HERE":
        logger.error("Please set your TELEGRAM_BOT_TOKEN environment variable!")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("events", send_event_list))

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_daily(
            send_weekly_updates,
            time=time(hour=10, minute=0, tzinfo=timezone.utc),
            days=(0,)  # 0 = Monday
        )
        logger.info("Weekly update job scheduled for Mondays at 10:00 UTC.")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
