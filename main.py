import logging
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue

# --- CONFIGURATION ---
# In Railway, you will set TELEGRAM_BOT_TOKEN in the Variables tab.
# For local testing, you can replace the default string below with your token.
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")

# --- YOUR EVENT DATA ---
# Since you are not using external APIs, you must maintain this list manually.
# Add new events here. The bot will automatically show events that haven't passed yet.
# Format: YYYY-MM-DD
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
            
    # Sort by date
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
    # Immediately send the list of upcoming events
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
    """
    Scheduled job to broadcast upcoming events.
    In this version, it broadcasts to a specific channel or group if configured,
    or you can loop through a stored list of user IDs.
    
    Since we are not using a database, this example sends to a designated 
    CHANNEL_ID if you set it, otherwise it skips.
    """
    # OPTIONAL: Set a channel ID in Railway Variables to receive weekly updates.
    # For example: -1001234567890
    target_chat_id = os.getenv("TARGET_CHANNEL_ID")
    
    if not target_chat_id:
        logger.info("No TARGET_CHANNEL_ID set. Skipping weekly broadcast.")
        return

    events = get_upcoming_events(days_ahead=7) # Get events for the next week
    
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

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("events", send_event_list))

    # --- SCHEDULE THE WEEKLY JOB ---
    # Run the send_weekly_updates function every Monday at 10:00 AM
    # (This uses the JobQueue extension)
    job_queue = application.job_queue
    if job_queue:
        # Schedule to run every Monday at 10:00 (UTC)
        # Adjust time as needed. Note: Railway uses UTC.
        job_queue.run_daily(
            send_weekly_updates,
            time=datetime.time(hour=10, minute=0, tzinfo=datetime.timezone.utc),
            days=(0,)  # 0 = Monday
        )
        logger.info("Weekly update job scheduled for Mondays at 10:00 UTC.")

    # Run the bot asynchronously
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
