"""Telegram surface. Long-polling (no public URL needed on a laptop demo).

The bot token is read from the vault (vault://telegram/bot), seeded once via
scripts/seed_credentials.py — same rule as every other credential: not in code,
not in the graph state, not visible to any model.
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import memory, vault
from .graph import ask

log = logging.getLogger("telegram")

# Telegram user id -> role; anyone not listed gets the most restricted role.
# For the demo this is a plain dict; production would be a users table.
# /role lets one account switch persona live (e.g. for a recorded demo) —
# every switch is itself just a normal in-memory dict write, nothing hidden.
ROLE_MAP: dict[int, str] = {}
DEFAULT_ROLE = "branch_manager"
KNOWN_ROLES = ("branch_manager", "barista", "ops_manager")


async def _handle_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args or []
    if not args or args[0] not in KNOWN_ROLES:
        current = ROLE_MAP.get(user.id, DEFAULT_ROLE)
        await update.message.reply_text(
            f"Current role: {current}\nUsage: /role <{'|'.join(KNOWN_ROLES)}>"
        )
        return
    ROLE_MAP[user.id] = args[0]
    log.info("telegram user %s (%s) switched role -> %s", user.id, user.username, args[0])
    await update.message.reply_text(f"Role set to *{args[0]}*.", parse_mode="Markdown")


async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    role = ROLE_MAP.get(user.id, DEFAULT_ROLE)
    log.info("telegram message from %s (%s) role=%s", user.id, user.username, role)

    result = await asyncio.to_thread(
        ask, update.message.text, user_id=f"tg:{user.id}", user_role=role
    )
    await update.message.reply_text(result["response"])


async def _handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Channel posts (bot must be a channel admin to receive them) are captured
    into organizational memory — queryable later via the search_team_notes
    capability. The bot does not reply in the channel."""
    post = update.channel_post
    if not post or not post.text:
        return
    chat = post.chat
    note_id = await asyncio.to_thread(
        memory.add_note, post.text,
        source=f"telegram-channel:{chat.title or chat.id}",
        author=str(post.author_signature or ""),
    )
    log.info("captured channel post from '%s' -> note %s", chat.title, note_id)


def run() -> None:
    token = vault._load_store().get("vault://telegram/bot")
    if not token:
        raise SystemExit(
            "no telegram token in vault — run scripts/seed_credentials.py first"
        )
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("role", _handle_role_command))
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.TEXT, _handle_channel_post))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.ChatType.CHANNEL, _handle))
    log.info("telegram bot polling…")
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
