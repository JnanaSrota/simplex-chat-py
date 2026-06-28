"""
AI bot powered by Groq + Llama 3.

Prerequisites:
    pip install simplex-chat-py
    export GROQ_API_KEY=gsk_...

Run:
    python examples/ai_bot.py

The bot maintains a per-contact conversation history so the LLM has context.
"""

import asyncio
import json
import logging
import os
from http.client import HTTPSConnection
from collections import defaultdict

from simplex_chat import SimplexBot, Contact, Message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    raise SystemExit("Set the GROQ_API_KEY environment variable first.")

SYSTEM_PROMPT = (
    "You are a helpful assistant reachable via SimpleX Chat — "
    "a private, end-to-end encrypted messaging app with no user identifiers. "
    "Be concise. Respond in plain text (no markdown)."
)
MODEL = "llama3-8b-8192"
MAX_HISTORY = 10   # messages to keep per contact
MAX_TOKENS = 512

# Per-contact message history: contact_id -> [{"role": ..., "content": ...}]
history: dict[int, list[dict]] = defaultdict(list)


def groq_chat(messages: list[dict]) -> str:
    """Call Groq API synchronously (runs in thread pool)."""
    conn = HTTPSConnection("api.groq.com")
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "max_tokens": MAX_TOKENS,
    })
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
    }
    conn.request("POST", "/openai/v1/chat/completions", payload, headers)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data["choices"][0]["message"]["content"].strip()


bot = SimplexBot(port=5225)


@bot.on_connect
async def welcome(contact: Contact) -> None:
    print(f"[+] New contact: {contact.display_name}")
    await contact.send(
        "Hi! I'm an AI assistant powered by Groq + Llama 3, "
        "running on SimpleX Chat.\n"
        "Ask me anything. Type /reset to clear conversation history."
    )


@bot.on_message
async def handle(msg: Message) -> None:
    if not msg.is_direct or msg.contact_id is None:
        return  # only handle direct messages for now

    print(f"[DM] {msg.sender_name}: {msg.text}")
    contact_id = msg.contact_id

    # Handle /reset command
    if msg.text.strip().lower() == "/reset":
        history[contact_id].clear()
        await msg.send("Conversation history cleared.")
        return

    # Append user message to history
    history[contact_id].append({"role": "user", "content": msg.text})

    # Trim to MAX_HISTORY
    if len(history[contact_id]) > MAX_HISTORY:
        history[contact_id] = history[contact_id][-MAX_HISTORY:]

    try:
        loop = asyncio.get_event_loop()
        reply = await loop.run_in_executor(
            None, groq_chat, list(history[contact_id])
        )
    except Exception as exc:
        logger = logging.getLogger(__name__)
        logger.exception("Groq API error")
        await msg.send(f"Sorry, something went wrong: {exc}")
        return

    # Append assistant reply to history
    history[contact_id].append({"role": "assistant", "content": reply})

    await msg.reply(reply)
    print(f"[AI → {msg.sender_name}]: {reply[:80]}...")


if __name__ == "__main__":
    asyncio.run(bot.run())
