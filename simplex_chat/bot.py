"""
High-level SimplexBot with a decorator-based API.

Quick start::

    from simplex_chat import SimplexBot, Message

    bot = SimplexBot()

    @bot.on_message
    async def handle(msg: Message) -> None:
        await msg.reply(f"Echo: {msg.text}")

    import asyncio
    asyncio.run(bot.run())
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from .client import SimplexClient

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Data models
# ------------------------------------------------------------------ #


@dataclass
class Message:
    """An incoming text message delivered to the bot.

    Attributes:
        text:            The message text.
        contact_id:      Contact ID for direct messages (None in groups).
        group_id:        Group ID for group messages (None in DMs).
        group_member_id: Sender's group member ID (None in DMs).
        sender_name:     Display name of the sender.
        item_id:         Internal chat item ID (use for quoting/deleting).
    """

    text: str
    contact_id: int | None
    group_id: int | None
    group_member_id: int | None
    sender_name: str
    item_id: int | None
    _bot: "SimplexBot" = field(repr=False)

    # -- Convenience --

    @property
    def is_direct(self) -> bool:
        return self.contact_id is not None

    @property
    def is_group(self) -> bool:
        return self.group_id is not None

    async def reply(self, text: str) -> dict:
        """Quote-reply to this message."""
        if self.contact_id is not None:
            return await self._bot.client.send_message(
                self.sender_name, text, quoted_item_id=self.item_id
            )
        if self.group_id is not None:
            return await self._bot.client.send_group_message(
                self.group_id, text, quoted_item_id=self.item_id
            )
        raise RuntimeError("Cannot reply: message has no contact_id or group_id")

    async def send(self, text: str) -> dict:
        """Send a new message to the same chat (no quote)."""
        if self.contact_id is not None:
            return await self._bot.client.send_message(self.sender_name, text)
        if self.group_id is not None:
            return await self._bot.client.send_group_message(self.group_id, text)
        raise RuntimeError("Cannot send: message has no contact_id or group_id")

    async def react(self, emoji: str) -> dict:
        """Add an emoji reaction to this message."""
        reaction = {"tag": "emoji", "emoji": emoji}
        if self.contact_id is not None and self.item_id is not None:
            return await self._bot.client.react_to_message(
                self.sender_name, self.item_id, reaction
            )
        raise RuntimeError("React only supported on direct messages for now")


@dataclass
class Contact:
    """A connected contact.

    Attributes:
        contact_id:   Numeric contact ID.
        display_name: The contact's display name.
    """

    contact_id: int
    display_name: str
    _bot: "SimplexBot" = field(repr=False)

    async def send(self, text: str) -> dict:
        """Send a message to this contact."""
        return await self._bot.client.send_message(self.display_name, text)


# ------------------------------------------------------------------ #
# Handler type aliases
# ------------------------------------------------------------------ #

MessageHandler = Callable[[Message], Awaitable[None]]
ContactHandler = Callable[[Contact], Awaitable[None]]
RawEventHandler = Callable[[dict], Awaitable[None]]


# ------------------------------------------------------------------ #
# Bot
# ------------------------------------------------------------------ #


class SimplexBot:
    """High-level SimpleX Chat bot with a decorator-based event API.

    Usage::

        bot = SimplexBot(port=5225)

        @bot.on_message
        async def handle(msg: Message) -> None:
            await msg.reply("Hello!")

        asyncio.run(bot.run())
    """

    def __init__(self, host: str = "localhost", port: int = 5225) -> None:
        self.client = SimplexClient(host, port)
        self._user_id: int | None = None
        self._message_handlers: list[MessageHandler] = []
        self._connect_handlers: list[ContactHandler] = []
        self._raw_handlers: list[RawEventHandler] = []
        self._running = False

    # ------------------------------------------------------------------ #
    # Decorators
    # ------------------------------------------------------------------ #

    def on_message(self, fn: MessageHandler) -> MessageHandler:
        """Register a handler called for every incoming text message.

        The handler receives a :class:`Message` object::

            @bot.on_message
            async def handle(msg: Message) -> None:
                await msg.reply(f"You said: {msg.text}")
        """
        self._message_handlers.append(fn)
        return fn

    def on_connect(self, fn: ContactHandler) -> ContactHandler:
        """Register a handler called when a new contact connects.

        The handler receives a :class:`Contact` object::

            @bot.on_connect
            async def welcome(contact: Contact) -> None:
                await contact.send("Hi! Thanks for connecting.")
        """
        self._connect_handlers.append(fn)
        return fn

    def on_event(self, fn: RawEventHandler) -> RawEventHandler:
        """Register a handler for raw CLI events (advanced use).

        Receives the full event dict from the WebSocket::

            @bot.on_event
            async def debug(event: dict) -> None:
                print(event)
        """
        self._raw_handlers.append(fn)
        return fn

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Connect to the CLI and resolve the active user ID."""
        await self.client.connect()

        resp = await self.client.get_active_user()
        if resp.get("type") != "activeUser":
            raise RuntimeError(f"Could not get active user: {resp}")

        self._user_id = resp["user"]["userId"]
        logger.info("Bot running as userId=%s", self._user_id)

        self.client.add_event_handler(self._dispatch)

    async def stop(self) -> None:
        """Disconnect from the CLI."""
        self._running = False
        await self.client.disconnect()

    async def run(self) -> None:
        """Start the bot and block until a KeyboardInterrupt."""
        await self.start()
        self._running = True
        logger.info("Bot is running. Press Ctrl+C to stop.")
        try:
            while self._running:
                await asyncio.sleep(1)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await self.stop()

    # ------------------------------------------------------------------ #
    # Setup helpers
    # ------------------------------------------------------------------ #

    async def setup_address(
        self,
        auto_accept: bool = True,
        accept_incognito: bool = False,
    ) -> str:
        """Create (or retrieve) the bot's address and optionally enable auto-accept.

        Returns the full connection link (share this for people to connect).

        Example::

            link = await bot.setup_address()
            print(f"Connect to me: {link}")
        """
        if self._user_id is None:
            raise RuntimeError("Bot not started. Call start() first.")

        # Try existing address
        resp = await self.client.show_address(self._user_id)

        if resp.get("type") == "chatCmdError":
            # No address yet – create one
            resp = await self.client.create_address(self._user_id)

        if auto_accept:
            settings = {
                "autoAccept": {
                    "autoAccept": True,
                    "acceptIncognito": accept_incognito,
                    "autoReply": None,
                }
            }
            await self.client.set_address_settings(self._user_id, settings)

        # Extract the link string from either response shape
        link_obj = resp.get("connLinkContact") or resp.get(
            "contactLink", {}
        ).get("connReqContact", {})

        if isinstance(link_obj, dict):
            return (
                link_obj.get("connFullLink")
                or link_obj.get("connShortLink")
                or str(link_obj)
            )
        return str(link_obj)

    @property
    def user_id(self) -> int:
        """The active user ID (available after start())."""
        if self._user_id is None:
            raise RuntimeError("Bot not started. Call start() first.")
        return self._user_id

    # ------------------------------------------------------------------ #
    # Event dispatch (internal)
    # ------------------------------------------------------------------ #

    async def _dispatch(self, event: dict) -> None:
        # Raw handlers first
        for handler in self._raw_handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("Error in raw event handler %r", handler.__name__)

        event_type = event.get("type")

        if event_type == "newChatItems":
            await self._handle_new_chat_items(event)
        elif event_type == "contactConnected":
            await self._handle_contact_connected(event)
        elif event_type == "contactRequest":
            await self._handle_contact_request(event)

    async def _handle_new_chat_items(self, event: dict) -> None:
        for item in event.get("chatItems", []):
            msg = self._parse_message(item)
            if msg is None:
                continue
            for handler in self._message_handlers:
                try:
                    await handler(msg)
                except Exception:
                    logger.exception(
                        "Error in message handler %r", handler.__name__
                    )

    async def _handle_contact_connected(self, event: dict) -> None:
        contact_data = event.get("contact", {})
        contact = Contact(
            contact_id=contact_data["contactId"],
            display_name=contact_data.get("localDisplayName", ""),
            _bot=self,
        )
        for handler in self._connect_handlers:
            try:
                await handler(contact)
            except Exception:
                logger.exception(
                    "Error in connect handler %r", handler.__name__
                )

    async def _handle_contact_request(self, event: dict) -> None:
        """Auto-accept contact requests not handled by CLI settings."""
        req = event.get("contactRequest", {})
        req_id = req.get("contactRequestId")
        if req_id:
            logger.info("Auto-accepting contact request %s", req_id)
            await self.client.accept_contact(req_id)

    def _parse_message(self, item: dict) -> Message | None:
        chat_info = item.get("chatInfo", {})
        chat_item = item.get("chatItem", {})
        chat_dir = chat_item.get("chatDir", {})
        content = chat_item.get("content", {})

        # Only process received messages
        dir_type = chat_dir.get("type", "")
        if dir_type not in ("directRcv", "groupRcv"):
            return None
        
        # Skip messages sent by us (avoids echo loops when connected to same profile)
        if chat_item.get("sent"):
            return None

        # Only handle text for basic message handlers
        msg_content = content.get("msgContent", {})
        if msg_content.get("type") != "text":
            return None

        text = msg_content.get("text", "").strip()
        if not text:
            return None
        
         # Stop self‑echo loop when bot and phone share the same profile
        if text.startswith("Echo:"):
            return None

        item_id: int | None = chat_item.get("meta", {}).get("itemId")
        chat_type = chat_info.get("type")

        if chat_type == "direct":
            contact = chat_info.get("contact", {})
            return Message(
                text=text,
                contact_id=contact.get("contactId"),
                group_id=None,
                group_member_id=None,
                sender_name=contact.get("localDisplayName", ""),
                item_id=item_id,
                _bot=self,
            )

        if chat_type == "group":
            group_info = chat_info.get("groupInfo", {})
            group_member = chat_dir.get("groupMember", {})
            return Message(
                text=text,
                contact_id=None,
                group_id=group_info.get("groupId"),
                group_member_id=group_member.get("groupMemberId"),
                sender_name=group_member.get("localDisplayName", ""),
                item_id=item_id,
                _bot=self,
            )

        return None
