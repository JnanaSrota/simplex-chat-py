#!/usr/bin/env python3
"""
SimpleX Echo Bot — a minimal bot that echoes all incoming messages.

Requirements:
    pip install websockets

Usage:
    1. Start simplex-chat as a WebSocket server:
       simplex-chat -p 5225
    2. In the same terminal, enable auto_accept and get your address:
       /auto_accept on
       /address        (copy this address)
    3. Run the bot:
       python echo_bot.py
    4. Connect your SimpleX app to the copied address and send a message.
"""

import asyncio
import json
import logging
import sys
import traceback
import uuid

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echo_bot")


class EchoBot:
    def __init__(self, port=5225):
        self.uri = f"ws://localhost:{port}"

    async def run(self):
        async with websockets.connect(self.uri) as ws:
            logger.info("Connected. Waiting for messages...")
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.error("Invalid JSON: %s", raw)
                    continue

                resp = data.get("resp", {})
                if resp.get("type") != "newChatItems":
                    continue

                for item in resp.get("chatItems", []):
                    chat = item.get("chatItem", {})
                    # skip own messages to avoid loops
                    if chat.get("sent"):
                        continue

                    content = chat.get("content", {})
                    text = content.get("msgContent", {}).get("text", "")
                    if not text:
                        continue

                   # Stop self‑echo loop when bot and phone share the same profile
                    if text.startswith("Echo:"):
                        continue

                    contact = item.get("chatInfo", {}).get("contact", {})
                    # The contact's display name is required for @ sending
                    name = (
                        contact.get("localDisplayName")
                        or contact.get("displayName")
                        or contact.get("profile", {}).get("displayName")
                        or ""
                    )
                    if not name:
                        logger.warning("Could not determine contact name, skipping")
                        continue

                    logger.info("Received: %s (from %s)", text, name)
                    reply = f"Echo: {text}"
                    cmd = f"@{name} {reply}"
                    await ws.send(
                        json.dumps({"corrId": str(uuid.uuid4()), "cmd": cmd})
                    )
                    logger.debug("Sent: %s", cmd)


if __name__ == "__main__":
    asyncio.run(EchoBot().run())
