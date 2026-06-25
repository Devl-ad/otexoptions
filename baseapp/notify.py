import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def notify_admins(message: str):
    """Send a message to every admin's Telegram chat."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("Telegram bot token not configured — skipping admin notify.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for chat_id in settings.TELEGRAM_ADMIN_CHAT_IDS:
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=5,
            )
        except Exception as e:
            logger.error(f"Telegram notify failed for chat {chat_id}: {e}")
