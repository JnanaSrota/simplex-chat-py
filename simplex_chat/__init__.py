"""
simplex-chat-py — Python client library for the SimpleX Chat bot API.

The :class:`SimplexBot` class provides a high-level decorator-based API::

    from simplex_chat import SimplexBot, Message

    bot = SimplexBot()

    @bot.on_message
    async def handle(msg: Message) -> None:
        await msg.reply(f"Echo: {msg.text}")

    import asyncio
    asyncio.run(bot.run())

For lower-level access use :class:`SimplexClient` directly.
"""

from .bot import Contact, Message, SimplexBot
from .client import SimplexClient

__all__ = [
    "SimplexBot",
    "SimplexClient",
    "Message",
    "Contact",
]

__version__ = "0.1.0"
