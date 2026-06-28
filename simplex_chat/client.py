"""
Low-level WebSocket client for the SimpleX Chat CLI bot API.

Command syntax is taken verbatim from:
https://github.com/simplex-chat/simplex-chat/blob/stable/bots/api/COMMANDS.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class SimplexClient:
    """Raw WebSocket client for the SimpleX Chat CLI.

    Run the CLI as a WebSocket server first::

        simplex-chat -p 5225

    Then connect::

        client = SimplexClient()
        await client.connect()
    """

    def __init__(self, host: str = "localhost", port: int = 5225) -> None:
        self.uri = f"ws://{host}:{port}"
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._event_handlers: list[Callable[[dict], Awaitable[None]]] = []
        self._listen_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """Open the WebSocket connection to the CLI."""
        self._ws = await websockets.connect(self.uri)
        self._listen_task = asyncio.create_task(self._listen())
        logger.info("Connected to SimpleX CLI at %s", self.uri)

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        logger.info("Disconnected from SimpleX CLI")

    async def _listen(self) -> None:
        try:
            async for raw in self._ws:  # type: ignore[union-attr]
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as exc:
                    logger.warning("Could not parse WS message: %s", exc)
                    continue

                corr_id: str | None = data.get("corrId")
                resp: dict = data.get("resp", {})

                if corr_id and corr_id in self._pending:
                    fut = self._pending.pop(corr_id)
                    if not fut.done():
                        fut.set_result(resp)
                else:
                    for handler in self._event_handlers:
                        asyncio.create_task(handler(resp))
        except ConnectionClosed:
            logger.info("WebSocket connection closed")
            # Fail all pending futures
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("WebSocket closed"))
            self._pending.clear()

    # ------------------------------------------------------------------ #
    # Core send
    # ------------------------------------------------------------------ #

    async def send_cmd(self, cmd: str, timeout: float = 30.0) -> dict[str, Any]:
        """Send a CLI command string and await its response."""
        if self._ws is None:
            raise RuntimeError("Not connected. Call connect() first.")

        corr_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[corr_id] = fut

        payload = json.dumps({"corrId": corr_id, "cmd": cmd})
        await self._ws.send(payload)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(corr_id, None)
            raise TimeoutError(f"Command timed out after {timeout}s: {cmd!r}")

    def add_event_handler(
        self, handler: Callable[[dict], Awaitable[None]]
    ) -> None:
        self._event_handlers.append(handler)

    def remove_event_handler(
        self, handler: Callable[[dict], Awaitable[None]]
    ) -> None:
        self._event_handlers.discard(handler)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # User profile commands
    # ------------------------------------------------------------------ #

    async def get_active_user(self) -> dict:
        """Get active user profile. (ShowActiveUser)"""
        return await self.send_cmd("/user")

    async def list_users(self) -> dict:
        """Get all user profiles. (ListUsers)"""
        return await self.send_cmd("/users")

    async def update_profile(self, user_id: int, profile: dict) -> dict:
        """Update user profile. (APIUpdateProfile)

        profile keys: displayName, fullName, image (base64), preferences
        """
        return await self.send_cmd(
            f"/_profile {user_id} {json.dumps(profile)}"
        )

    # ------------------------------------------------------------------ #
    # Address commands
    # ------------------------------------------------------------------ #

    async def create_address(self, user_id: int) -> dict:
        """Create bot address. (APICreateMyAddress)"""
        return await self.send_cmd(f"/_address {user_id}")

    async def delete_address(self, user_id: int) -> dict:
        """Delete bot address. (APIDeleteMyAddress)"""
        return await self.send_cmd(f"/_delete_address {user_id}")

    async def show_address(self, user_id: int) -> dict:
        """Get bot address and settings. (APIShowMyAddress)"""
        return await self.send_cmd(f"/_show_address {user_id}")

    async def set_profile_address(self, user_id: int, enable: bool) -> dict:
        """Add/remove address from bot profile. (APISetProfileAddress)"""
        flag = "on" if enable else "off"
        return await self.send_cmd(f"/_profile_address {user_id} {flag}")

    async def set_address_settings(
        self, user_id: int, settings: dict
    ) -> dict:
        """Set address settings (auto-accept etc.). (APISetAddressSettings)

        Example settings for auto-accept::

            {
                "autoAccept": {
                    "autoAccept": True,
                    "acceptIncognito": False,
                    "autoReply": None,
                }
            }
        """
        return await self.send_cmd(
            f"/_address_settings {user_id} {json.dumps(settings)}"
        )

    # ------------------------------------------------------------------ #
    # Message commands
    # ------------------------------------------------------------------ #

    async def send_message(
        self,
        contact_name: str,
        text: str,
        quoted_item_id: int | None = None,
        ttl: int | None = None,
    ) -> dict:
        """Send a direct text message. (APISendMessages)"""
        msg: dict[str, Any] = {"msgContent": {"type": "text", "text": text}}
        if quoted_item_id is not None:
            msg["quotedItemId"] = quoted_item_id

        ttl_part = f" ttl={ttl}" if ttl is not None else ""
        return await self.send_cmd(
            f"/_send @{contact_name}{ttl_part} json {json.dumps([msg])}"
        )

    async def send_group_message(
        self,
        group_id: int,
        text: str,
        quoted_item_id: int | None = None,
        ttl: int | None = None,
    ) -> dict:
        """Send a text message to a group. (APISendMessages)"""
        msg: dict[str, Any] = {"msgContent": {"type": "text", "text": text}}
        if quoted_item_id is not None:
            msg["quotedItemId"] = quoted_item_id

        ttl_part = f" ttl={ttl}" if ttl is not None else ""
        return await self.send_cmd(
            f"/_send #{group_id}{ttl_part} json {json.dumps([msg])}"
        )

    async def update_message(
        self,
        contact_name: str,
        item_id: int,
        new_text: str,
    ) -> dict:
        """Edit a direct message. (APIUpdateChatItem)"""
        updated = {"msgContent": {"type": "text", "text": new_text}}
        return await self.send_cmd(
            f"/_update item @{contact_name} {item_id} json {json.dumps(updated)}"
        )

    async def delete_message(
        self,
        contact_name: str,
        item_id: int,
        mode: str = "broadcast",
    ) -> dict:
        """Delete a direct message. (APIDeleteChatItem)

        mode: broadcast | internal | internalMark | history
        """
        return await self.send_cmd(
            f"/_delete item @{contact_name} {item_id} {mode}"
        )

    async def delete_group_message(
        self,
        group_id: int,
        item_id: int,
        mode: str = "broadcast",
    ) -> dict:
        """Delete a group message. (APIDeleteChatItem)"""
        return await self.send_cmd(
            f"/_delete item #{group_id} {item_id} {mode}"
        )

    async def react_to_message(
        self,
        contact_name: str,
        item_id: int,
        reaction: dict,
        add: bool = True,
    ) -> dict:
        """Add/remove reaction on a direct message. (APIChatItemReaction)

        Example reaction: {"tag": "emoji", "emoji": "👍"}
        """
        flag = "on" if add else "off"
        return await self.send_cmd(
            f"/_reaction @{contact_name} {item_id} {flag} {json.dumps(reaction)}"
        )

    # ------------------------------------------------------------------ #
    # File commands
    # ------------------------------------------------------------------ #

    async def receive_file(
        self,
        file_id: int,
        user_approved_relays: bool = False,
        store_encrypted: bool | None = None,
        file_path: str | None = None,
    ) -> dict:
        """Accept an incoming file transfer. (ReceiveFile)"""
        cmd = f"/freceive {file_id}"
        if user_approved_relays:
            cmd += " approved_relays=on"
        if store_encrypted is not None:
            cmd += f" encrypt={'on' if store_encrypted else 'off'}"
        if file_path is not None:
            cmd += f" {file_path}"
        return await self.send_cmd(cmd)

    async def cancel_file(self, file_id: int) -> dict:
        """Cancel a file transfer. (CancelFile)"""
        return await self.send_cmd(f"/fcancel {file_id}")

    # ------------------------------------------------------------------ #
    # Contact commands
    # ------------------------------------------------------------------ #

    async def list_contacts(self, user_id: int) -> dict:
        """Get contacts. (APIListContacts)"""
        return await self.send_cmd(f"/_contacts {user_id}")

    async def accept_contact(self, contact_req_id: int) -> dict:
        """Accept a contact request. (APIAcceptContact)"""
        return await self.send_cmd(f"/_accept {contact_req_id}")

    async def reject_contact(self, contact_req_id: int) -> dict:
        """Reject a contact request. (APIRejectContact)"""
        return await self.send_cmd(f"/_reject {contact_req_id}")

    async def connect_via_link(self, link: str) -> dict:
        """Connect via a SimpleX link. (Connect)"""
        return await self.send_cmd(f"/connect {link}")

    # ------------------------------------------------------------------ #
    # Group commands
    # ------------------------------------------------------------------ #

    async def list_groups(self, user_id: int, search: str | None = None) -> dict:
        """Get groups. (APIListGroups)"""
        cmd = f"/_groups {user_id}"
        if search is not None:
            cmd += f" {search}"
        return await self.send_cmd(cmd)

    async def list_members(self, group_id: int) -> dict:
        """Get group members. (APIListMembers)"""
        return await self.send_cmd(f"/_members #{group_id}")

    async def add_member(
        self, group_id: int, contact_id: int, role: str = "member"
    ) -> dict:
        """Add a contact to a group. (APIAddMember)

        role: relay | observer | author | member | moderator | admin | owner
        """
        return await self.send_cmd(
            f"/_add #{group_id} {contact_id} {role}"
        )

    async def remove_members(
        self,
        group_id: int,
        member_ids: list[int],
        with_messages: bool = False,
    ) -> dict:
        """Remove members from a group. (APIRemoveMembers)"""
        ids = ",".join(map(str, member_ids))
        suffix = " messages=on" if with_messages else ""
        return await self.send_cmd(f"/_remove #{group_id} {ids}{suffix}")

    async def set_member_role(
        self, group_id: int, member_ids: list[int], role: str
    ) -> dict:
        """Set member role. (APIMembersRole)

        role: relay | observer | author | member | moderator | admin | owner
        """
        ids = ",".join(map(str, member_ids))
        return await self.send_cmd(
            f"/_member role #{group_id} {ids} {role}"
        )

    async def block_members(
        self, group_id: int, member_ids: list[int], blocked: bool = True
    ) -> dict:
        """Block/unblock members. (APIBlockMembersForAll)"""
        ids = ",".join(map(str, member_ids))
        flag = "on" if blocked else "off"
        return await self.send_cmd(
            f"/_block #{group_id} {ids} blocked={flag}"
        )

    async def join_group(self, group_id: int) -> dict:
        """Accept a group invitation. (APIJoinGroup)"""
        return await self.send_cmd(f"/_join #{group_id}")

    async def leave_group(self, group_id: int) -> dict:
        """Leave a group. (APILeaveGroup)"""
        return await self.send_cmd(f"/_leave #{group_id}")

    async def create_group_link(
        self, group_id: int, role: str = "member"
    ) -> dict:
        """Create a group invite link. (APICreateGroupLink)"""
        return await self.send_cmd(f"/_create link #{group_id} {role}")

    async def get_group_link(self, group_id: int) -> dict:
        """Get the group invite link. (APIGetGroupLink)"""
        return await self.send_cmd(f"/_get link #{group_id}")

    async def delete_group_link(self, group_id: int) -> dict:
        """Delete the group invite link. (APIDeleteGroupLink)"""
        return await self.send_cmd(f"/_delete link #{group_id}")

    async def moderate_message(
        self, group_id: int, item_ids: list[int]
    ) -> dict:
        """Moderate (delete) member messages in a group. (APIDeleteMemberChatItem)"""
        ids = ",".join(map(str, item_ids))
        return await self.send_cmd(
            f"/_delete member item #{group_id} {ids}"
        )
