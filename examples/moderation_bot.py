"""
Basic group moderation bot.

Watches a group for banned words and removes the message + warns the user.
Also supports admin commands like /kick and /role.

Usage:
    1. Add the bot to your group as Admin.
    2. python examples/moderation_bot.py

Commands (admin only):
    /kick @username    — remove a member
    /warn @username    — send a warning message
"""

import asyncio
import logging

from simplex_chat import SimplexBot, Message

logging.basicConfig(level=logging.INFO)

# ---- Config ----
TARGET_GROUP_ID = 1          # change to your group ID
ADMIN_NAMES: set[str] = {"your_admin_name"}   # localDisplayName of admins
BANNED_WORDS: list[str] = ["spam", "scam"]
WARN_LIMIT = 3               # remove after this many warnings

# ---- State ----
warn_count: dict[int, int] = {}   # group_member_id -> count

bot = SimplexBot(port=5225)


@bot.on_message
async def moderate(msg: Message) -> None:
    if not msg.is_group or msg.group_id != TARGET_GROUP_ID:
        return

    text_lower = msg.text.lower()

    # Handle admin commands
    if msg.sender_name in ADMIN_NAMES:
        if text_lower.startswith("/kick "):
            target = msg.text.split(maxsplit=1)[1].lstrip("@")
            await msg.send(f"⚠️ Kick command received for @{target} — not yet implemented.")
            return

    # Check banned words
    flagged = [w for w in BANNED_WORDS if w in text_lower]
    if not flagged:
        return

    member_id = msg.group_member_id
    if member_id is None:
        return

    # Delete the offending message
    if msg.item_id:
        await bot.client.moderate_message(TARGET_GROUP_ID, [msg.item_id])

    # Increment warning count
    warn_count[member_id] = warn_count.get(member_id, 0) + 1
    count = warn_count[member_id]

    if count >= WARN_LIMIT:
        await bot.client.remove_members(TARGET_GROUP_ID, [member_id])
        await bot.client.send_group_message(
            TARGET_GROUP_ID,
            f"🚫 @{msg.sender_name} was removed after {WARN_LIMIT} warnings.",
        )
        warn_count.pop(member_id, None)
    else:
        await bot.client.send_group_message(
            TARGET_GROUP_ID,
            f"⚠️ @{msg.sender_name}: warning {count}/{WARN_LIMIT}. "
            f"Message removed (contained: {', '.join(flagged)}).",
        )

    logging.getLogger(__name__).info(
        "Flagged message from %s (warning %s/%s): %s",
        msg.sender_name, count, WARN_LIMIT, msg.text,
    )


if __name__ == "__main__":
    asyncio.run(bot.run())
