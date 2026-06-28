# simplex-chat-py

Python client library for the [SimpleX Chat](https://simplex.chat) bot API.

SimpleX is the first messaging network with no user identifiers — 100% private by design. This library lets you build bots that connect to the SimpleX Chat CLI over its local WebSocket API.

[![PyPI](https://img.shields.io/pypi/v/simplex-chat-py)](https://pypi.org/project/simplex-chat-py/)
[![Python](https://img.shields.io/pypi/pyversions/simplex-chat-py)](https://pypi.org/project/simplex-chat-py/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Prerequisites

**1. Install the SimpleX Chat CLI:**

```bash
curl -o- https://raw.githubusercontent.com/simplex-chat/simplex-chat/stable/install.sh | bash
```

**2. Start the WebSocket server (create a profile on first run):**

```bash
simplex-chat -p 5225
```

**3. In a second terminal, open the interactive CLI to get your bot's address and enable auto-accept:**

```bash
simplex-chat
/address
/auto_accept on
/exit
```

**4. Install this library:**

```bash
pip install simplex-chat-py
```

---

## Quick start — echo bot

```python
import asyncio
from simplex_chat import SimplexBot, Contact, Message

bot = SimplexBot(port=5225)

@bot.on_connect
async def welcome(contact: Contact) -> None:
    await contact.send("Hi! I echo everything you send me.")

@bot.on_message
async def echo(msg: Message) -> None:
    await msg.reply(f"Echo: {msg.text}")

asyncio.run(bot.run())
```

---

## Installation

```bash
pip install simplex-chat-py
```

Or from source:

```bash
git clone https://github.com/JnanaSrota/simplex-chat-py
cd simplex-chat-py
pip install -e .
```

---

## API reference

### `SimplexBot`

High-level bot with a decorator-based event API.

```python
bot = SimplexBot(host="localhost", port=5225)
```

#### Decorators

| Decorator | Called when | Receives |
|---|---|---|
| `@bot.on_message` | A text message arrives | `Message` |
| `@bot.on_connect` | A new contact connects | `Contact` |
| `@bot.on_event` | Any raw CLI event (advanced) | `dict` |

#### Lifecycle

```python
await bot.start()   # connect + resolve userId
await bot.run()     # start + block (Ctrl+C to stop)
await bot.stop()    # disconnect
```

#### Setup helper

```python
link = await bot.setup_address(auto_accept=True)
print(f"Connect to this bot: {link}")
```

---

### `Message`

Passed to `@bot.on_message` handlers.

| Attribute | Type | Description |
|---|---|---|
| `text` | `str` | Message text |
| `contact_id` | `int \| None` | Set for direct messages |
| `group_id` | `int \| None` | Set for group messages |
| `group_member_id` | `int \| None` | Sender's group member ID |
| `sender_name` | `str` | Display name of sender |
| `item_id` | `int \| None` | Chat item ID (for quoting/deleting) |
| `is_direct` | `bool` | True for DMs |
| `is_group` | `bool` | True for group messages |

| Method | Description |
|---|---|
| `await msg.reply(text)` | Quote-reply to this message |
| `await msg.send(text)` | Send new message to same chat (no quote) |
| `await msg.react(emoji)` | Add emoji reaction (DMs only) |

---

### `Contact`

Passed to `@bot.on_connect` handlers.

| Attribute | Type | Description |
|---|---|---|
| `contact_id` | `int` | Numeric contact ID |
| `display_name` | `str` | Contact's display name |

| Method | Description |
|---|---|
| `await contact.send(text)` | Send a message to this contact |

---

### `SimplexClient`

Low-level client — direct access to all CLI commands.

```python
from simplex_chat import SimplexClient

client = SimplexClient(port=5225)
await client.connect()

user = await client.get_active_user()
user_id = user["user"]["userId"]

await client.send_message("alice", text="Hello!")
await client.send_group_message(group_id=3, text="Hello group!")
```

All commands from [bots/api/COMMANDS.md](https://github.com/simplex-chat/simplex-chat/blob/stable/bots/api/COMMANDS.md) are implemented:

| Method | API command |
|---|---|
| `create_address(user_id)` | `APICreateMyAddress` |
| `show_address(user_id)` | `APIShowMyAddress` |
| `set_address_settings(user_id, settings)` | `APISetAddressSettings` |
| `send_message(contact_name, text)` | `APISendMessages` |
| `send_group_message(group_id, text)` | `APISendMessages` |
| `update_message(contact_name, item_id, text)` | `APIUpdateChatItem` |
| `delete_message(contact_name, item_id)` | `APIDeleteChatItem` |
| `react_to_message(contact_name, item_id, reaction)` | `APIChatItemReaction` |
| `receive_file(file_id)` | `ReceiveFile` |
| `list_contacts(user_id)` | `APIListContacts` |
| `accept_contact(req_id)` | `APIAcceptContact` |
| `reject_contact(req_id)` | `APIRejectContact` |
| `list_groups(user_id)` | `APIListGroups` |
| `list_members(group_id)` | `APIListMembers` |
| `add_member(group_id, contact_id, role)` | `APIAddMember` |
| `remove_members(group_id, member_ids)` | `APIRemoveMembers` |
| `set_member_role(group_id, member_ids, role)` | `APIMembersRole` |
| `block_members(group_id, member_ids)` | `APIBlockMembersForAll` |
| `join_group(group_id)` | `APIJoinGroup` |
| `leave_group(group_id)` | `APILeaveGroup` |
| `create_group_link(group_id, role)` | `APICreateGroupLink` |
| `moderate_message(group_id, item_ids)` | `APIDeleteMemberChatItem` |
| `update_profile(user_id, profile)` | `APIUpdateProfile` |

---

## Examples

| File | Description |
|---|---|
| [`examples/echo_bot.py`](examples/echo_bot.py) | Echo every message back |
| [`examples/ai_bot.py`](examples/ai_bot.py) | AI assistant using Groq + Llama 3 (with per-contact history) |
| [`examples/moderation_bot.py`](examples/moderation_bot.py) | Group moderation: remove banned words, warn users |

### AI bot

```bash
export GROQ_API_KEY=gsk_...
python examples/ai_bot.py
```

---

## Running tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

---

## Contributing

PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT
