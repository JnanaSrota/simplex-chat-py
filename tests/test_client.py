"""
Unit tests for simplex-chat-py.

These tests mock the WebSocket connection and validate:
- Command string formatting (must match COMMANDS.md exactly)
- Message parsing from raw events
- Bot handler dispatch
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from simplex_chat.client import SimplexClient
from simplex_chat.bot import SimplexBot, Message


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ #
# Command string tests (match COMMANDS.md Python syntax exactly)
# ------------------------------------------------------------------ #

class TestCommandStrings(unittest.TestCase):
    """Verify that SimplexClient produces the exact command strings
    documented in bots/api/COMMANDS.md."""

    def setUp(self):
        self.client = SimplexClient()
        self.sent: list[str] = []

        async def fake_send(payload: str) -> None:
            data = json.loads(payload)
            self.sent.append(data["cmd"])

        mock_ws = AsyncMock()
        mock_ws.send = fake_send
        self.client._ws = mock_ws

        # Patch _listen to do nothing
        self.client._listen_task = MagicMock()

        # Pre-fill a future for every send_cmd call
        self._patch_pending()

    def _patch_pending(self):
        """Auto-resolve pending futures so send_cmd doesn't hang."""
        original_send_cmd = self.client.send_cmd

        async def patched_send_cmd(cmd: str, timeout: float = 30.0):
            import uuid
            corr_id = str(uuid.uuid4())
            loop = asyncio.get_event_loop()
            fut = loop.create_future()
            self.client._pending[corr_id] = fut
            payload = json.dumps({"corrId": corr_id, "cmd": cmd})
            await self.client._ws.send(payload)
            fut.set_result({"type": "cmdOk"})
            return await asyncio.wait_for(fut, 1.0)

        self.client.send_cmd = patched_send_cmd

    # Address commands
    def test_create_address(self):
        run(self.client.create_address(1))
        self.assertIn("/_address 1", self.sent)

    def test_show_address(self):
        run(self.client.show_address(42))
        self.assertIn("/_show_address 42", self.sent)

    def test_delete_address(self):
        run(self.client.delete_address(1))
        self.assertIn("/_delete_address 1", self.sent)

    def test_set_profile_address_on(self):
        run(self.client.set_profile_address(1, True))
        self.assertIn("/_profile_address 1 on", self.sent)

    def test_set_profile_address_off(self):
        run(self.client.set_profile_address(1, False))
        self.assertIn("/_profile_address 1 off", self.sent)

    # Message commands
    def test_send_message(self):
        run(self.client.send_message("prince", "hello"))
        cmd = self.sent[-1]
        self.assertTrue(cmd.startswith("/_send @prince json "), cmd)
        payload = json.loads(cmd.split(" json ", 1)[1])
        self.assertEqual(payload[0]["msgContent"]["text"], "hello")

    def test_send_message_with_quote(self):
        run(self.client.send_message("prince", "reply", quoted_item_id=42))
        cmd = self.sent[-1]
        payload = json.loads(cmd.split(" json ", 1)[1])
        self.assertEqual(payload[0]["quotedItemId"], 42)

    def test_send_group_message(self):
        run(self.client.send_group_message(3, "hi group"))
        cmd = self.sent[-1]
        self.assertTrue(cmd.startswith("/_send #3 json "), cmd)

    def test_delete_message(self):
        run(self.client.delete_message("prince", 99))
        self.assertIn("/_delete item @prince 99 broadcast", self.sent)

    def test_delete_message_internal(self):
        run(self.client.delete_message("prince", 99, mode="internal"))
        self.assertIn("/_delete item @prince 99 internal", self.sent)

    # Contact commands
    def test_list_contacts(self):
        run(self.client.list_contacts(1))
        self.assertIn("/_contacts 1", self.sent)

    def test_accept_contact(self):
        run(self.client.accept_contact(5))
        self.assertIn("/_accept 5", self.sent)

    def test_reject_contact(self):
        run(self.client.reject_contact(5))
        self.assertIn("/_reject 5", self.sent)

    # Group commands
    def test_list_groups(self):
        run(self.client.list_groups(1))
        self.assertIn("/_groups 1", self.sent)

    def test_list_members(self):
        run(self.client.list_members(10))
        self.assertIn("/_members #10", self.sent)

    def test_add_member(self):
        run(self.client.add_member(10, 7, "member"))
        self.assertIn("/_add #10 7 member", self.sent)

    def test_remove_members(self):
        run(self.client.remove_members(10, [7, 8]))
        self.assertIn("/_remove #10 7,8", self.sent)

    def test_remove_members_with_messages(self):
        run(self.client.remove_members(10, [7], with_messages=True))
        self.assertIn("/_remove #10 7 messages=on", self.sent)

    def test_set_member_role(self):
        run(self.client.set_member_role(10, [7], "moderator"))
        self.assertIn("/_member role #10 7 moderator", self.sent)

    def test_block_members(self):
        run(self.client.block_members(10, [7, 8]))
        self.assertIn("/_block #10 7,8 blocked=on", self.sent)

    def test_join_group(self):
        run(self.client.join_group(10))
        self.assertIn("/_join #10", self.sent)

    def test_leave_group(self):
        run(self.client.leave_group(10))
        self.assertIn("/_leave #10", self.sent)

    def test_create_group_link(self):
        run(self.client.create_group_link(10, "member"))
        self.assertIn("/_create link #10 member", self.sent)

    def test_receive_file(self):
        run(self.client.receive_file(3))
        self.assertIn("/freceive 3", self.sent)

    def test_receive_file_approved_relays(self):
        run(self.client.receive_file(3, user_approved_relays=True))
        self.assertIn("/freceive 3 approved_relays=on", self.sent)

    def test_cancel_file(self):
        run(self.client.cancel_file(3))
        self.assertIn("/fcancel 3", self.sent)

    def test_get_active_user(self):
        run(self.client.get_active_user())
        self.assertIn("/user", self.sent)

    def test_list_users(self):
        run(self.client.list_users())
        self.assertIn("/users", self.sent)


# ------------------------------------------------------------------ #
# Message parsing tests
# ------------------------------------------------------------------ #

class TestMessageParsing(unittest.TestCase):
    """Validate that bot._parse_message extracts fields correctly."""

    def setUp(self):
        self.bot = SimplexBot()
        self.bot._user_id = 1

    def _make_direct_item(
        self, text: str, contact_id: int = 7, item_id: int = 42
    ) -> dict:
        return {
            "chatInfo": {
                "type": "direct",
                "contact": {
                    "contactId": contact_id,
                    "localDisplayName": "alice",
                },
            },
            "chatItem": {
                "chatDir": {"type": "directRcv"},
                "meta": {"itemId": item_id},
                "content": {
                    "msgContent": {"type": "text", "text": text}
                },
            },
        }

    def _make_group_item(
        self, text: str, group_id: int = 3, member_id: int = 5, item_id: int = 99
    ) -> dict:
        return {
            "chatInfo": {
                "type": "group",
                "groupInfo": {
                    "groupId": group_id,
                    "localDisplayName": "testgroup",
                },
            },
            "chatItem": {
                "chatDir": {
                    "type": "groupRcv",
                    "groupMember": {
                        "groupMemberId": member_id,
                        "localDisplayName": "bob",
                    },
                },
                "meta": {"itemId": item_id},
                "content": {
                    "msgContent": {"type": "text", "text": text}
                },
            },
        }

    def test_parse_direct_message(self):
        item = self._make_direct_item("hello", contact_id=7, item_id=42)
        msg = self.bot._parse_message(item)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.text, "hello")
        self.assertEqual(msg.contact_id, 7)
        self.assertIsNone(msg.group_id)
        self.assertEqual(msg.item_id, 42)
        self.assertEqual(msg.sender_name, "alice")
        self.assertTrue(msg.is_direct)
        self.assertFalse(msg.is_group)

    def test_parse_group_message(self):
        item = self._make_group_item("hi group", group_id=3, member_id=5)
        msg = self.bot._parse_message(item)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.text, "hi group")
        self.assertIsNone(msg.contact_id)
        self.assertEqual(msg.group_id, 3)
        self.assertEqual(msg.group_member_id, 5)
        self.assertEqual(msg.sender_name, "bob")
        self.assertFalse(msg.is_direct)
        self.assertTrue(msg.is_group)

    def test_ignore_sent_messages(self):
        item = self._make_direct_item("hello")
        item["chatItem"]["chatDir"] = {"type": "directSnd"}
        msg = self.bot._parse_message(item)
        self.assertIsNone(msg)

    def test_ignore_non_text(self):
        item = self._make_direct_item("")
        item["chatItem"]["content"]["msgContent"] = {"type": "image"}
        msg = self.bot._parse_message(item)
        self.assertIsNone(msg)

    def test_ignore_empty_text(self):
        item = self._make_direct_item("   ")
        msg = self.bot._parse_message(item)
        self.assertIsNone(msg)


# ------------------------------------------------------------------ #
# Handler dispatch tests
# ------------------------------------------------------------------ #

class TestHandlerDispatch(unittest.IsolatedAsyncioTestCase):
    async def test_message_handler_called(self):
        bot = SimplexBot()
        bot._user_id = 1
        received: list[Message] = []

        @bot.on_message
        async def collect(msg: Message) -> None:
            received.append(msg)

        event = {
            "type": "newChatItems",
            "chatItems": [
                {
                    "chatInfo": {
                        "type": "direct",
                        "contact": {"contactId": 1, "localDisplayName": "test"},
                    },
                    "chatItem": {
                        "chatDir": {"type": "directRcv"},
                        "meta": {"itemId": 1},
                        "content": {"msgContent": {"type": "text", "text": "ping"}},
                    },
                }
            ],
        }

        await bot._dispatch(event)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].text, "ping")

    async def test_connect_handler_called(self):
        bot = SimplexBot()
        bot._user_id = 1
        connected = []

        @bot.on_connect
        async def on_conn(contact) -> None:
            connected.append(contact)

        event = {
            "type": "contactConnected",
            "contact": {"contactId": 5, "localDisplayName": "alice"},
        }

        await bot._dispatch(event)
        self.assertEqual(len(connected), 1)
        self.assertEqual(connected[0].contact_id, 5)
        self.assertEqual(connected[0].display_name, "alice")


if __name__ == "__main__":
    unittest.main(verbosity=2)
