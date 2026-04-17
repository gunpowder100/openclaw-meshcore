"""
MeshCore Client Module
Handles async serial communication with MeshCore devices (e.g., WIO Pro P1 Tracker).
Uses the meshcore Python library for the companion radio protocol.
"""

import asyncio
import logging
from typing import Callable, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("openclaw.meshcore")


@dataclass
class MeshMessage:
    """Represents an incoming or outgoing mesh message."""
    sender_id: str
    sender_name: str
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    is_group: bool = False
    channel: str = ""
    contact: object = None  # Reference to meshcore Contact object


# MeshCore text message limit
MESHCORE_CHAR_LIMIT = 133


def chunk_message(text: str, limit: int = MESHCORE_CHAR_LIMIT) -> List[str]:
    """
    Split a long AI response into MeshCore-compatible chunks.
    Tries to split on sentence boundaries, then word boundaries.
    Each chunk is prefixed with [n/N] if multiple chunks.
    """
    text = text.strip()
    if len(text) <= limit:
        return [text]

    # Reserve space for chunk prefix like "[1/3] "
    chunks = []
    # First pass: estimate chunk count for prefix sizing
    est_chunks = (len(text) // (limit - 8)) + 1
    prefix_len = len(f"[{est_chunks}/{est_chunks}] ")
    effective_limit = limit - prefix_len

    remaining = text
    while remaining:
        if len(remaining) <= effective_limit:
            chunks.append(remaining)
            break

        # Try to split at sentence boundary
        split_pos = effective_limit
        for sep in ['. ', '! ', '? ', '\n']:
            pos = remaining[:effective_limit].rfind(sep)
            if pos > effective_limit // 3:  # Don't split too early
                split_pos = pos + len(sep)
                break
        else:
            # Fall back to word boundary
            pos = remaining[:effective_limit].rfind(' ')
            if pos > effective_limit // 3:
                split_pos = pos + 1

        chunks.append(remaining[:split_pos].rstrip())
        remaining = remaining[split_pos:].lstrip()

    # Add chunk prefixes
    if len(chunks) > 1:
        total = len(chunks)
        chunks = [f"[{i+1}/{total}] {c}" for i, c in enumerate(chunks)]

    return chunks


class MeshCoreClient:
    """
    Async client for MeshCore companion radio protocol.
    Wraps the meshcore Python library for serial/BLE/TCP connections.
    """

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baud: int = 115200,
        debug: bool = False,
        redact_logs: bool = True,
    ):
        self.port = port
        self.baud = baud
        self.debug = debug
        self.redact_logs = redact_logs
        self._mc = None
        self._running = False
        self._on_message: Optional[Callable] = None
        self._contacts_cache: dict = {}

    async def connect(self):
        """Establish serial connection to MeshCore device."""
        try:
            from meshcore import MeshCore
            logger.info(f"Connecting to MeshCore device on {self.port} @ {self.baud}...")
            self._mc = await MeshCore.create_serial(
                self.port, self.baud, debug=self.debug
            )
            logger.info("MeshCore serial connection established.")

            # Fetch initial contacts
            await self._refresh_contacts()

            # Log device self-info
            if self._mc.self_info:
                logger.info(f"Device info: {self._mc.self_info}")

            return True

        except Exception as e:
            logger.error(f"Failed to connect to MeshCore device: {e}")
            raise

    async def _refresh_contacts(self):
        """Refresh the local contacts cache from the device."""
        try:
            ok = await self._mc.ensure_contacts()
            if ok:
                contacts = self._mc.contacts or {}
                self._contacts_cache = {}
                for key, contact in contacts.items():
                    pk = contact.get("public_key", key)
                    prefix = pk[:12]
                    self._contacts_cache[prefix] = contact
                    self._contacts_cache[pk] = contact
                    name = contact.get("adv_name", "")
                    if name:
                        self._contacts_cache[f"name:{name}"] = contact
                logger.info(f"Loaded {len(contacts)} contacts.")
            else:
                logger.warning("ensure_contacts returned False.")
        except Exception as e:
            logger.warning(f"Could not refresh contacts: {e}")

    def on_message(self, callback: Callable):
        """Register a callback for incoming mesh messages: async def handler(msg: MeshMessage)"""
        self._on_message = callback

    def _resolve_sender(self, pubkey_prefix: str):
        """Look up a contact by pubkey_prefix, return (contact_dict, display_name)."""
        contact = self._contacts_cache.get(pubkey_prefix)
        if contact:
            name = contact.get("adv_name", "") or pubkey_prefix[:4]
            return contact, name
        for key, c in self._contacts_cache.items():
            if key.startswith(pubkey_prefix) or pubkey_prefix.startswith(key[:12]):
                name = c.get("adv_name", "") or pubkey_prefix[:4]
                return c, name
        return None, pubkey_prefix[:4]

    async def start_listening(self):
        """Start the event loop that listens for incoming messages."""
        from meshcore.events import EventType

        if not self._mc:
            raise RuntimeError("Not connected. Call connect() first.")

        self._running = True
        logger.info("Listening for incoming MeshCore messages...")

        async def _handle_contact_msg(event):
            try:
                payload = event.payload
                pubkey_prefix = payload.get("pubkey_prefix", "unknown")
                text = payload.get("text", "")
                contact, sender_name = self._resolve_sender(pubkey_prefix)
                msg = MeshMessage(
                    sender_id=pubkey_prefix,
                    sender_name=sender_name,
                    text=text,
                    is_group=False,
                    channel="",
                    contact=contact,
                )
                if self.redact_logs:
                    logger.info(f"[RX DM] {msg.sender_name} ({msg.sender_id}): <redacted>")
                else:
                    logger.info(f"[RX DM] {msg.sender_name} ({msg.sender_id}): {msg.text}")
                if self._on_message:
                    await self._on_message(msg)
            except Exception as e:
                logger.error(f"Error handling contact message: {e}", exc_info=True)

        async def _handle_channel_msg(event):
            try:
                payload = event.payload
                channel_idx = payload.get("channel_idx", 0)
                text = payload.get("text", "")
                pubkey_prefix = payload.get("pubkey_prefix", "channel")
                contact, sender_name = self._resolve_sender(pubkey_prefix)
                msg = MeshMessage(
                    sender_id=pubkey_prefix,
                    sender_name=sender_name,
                    text=text,
                    is_group=True,
                    channel=str(channel_idx),
                    contact=contact,
                )
                if self.redact_logs:
                    logger.info(f"[RX CH{channel_idx}] {msg.sender_name}: <redacted>")
                else:
                    logger.info(f"[RX CH{channel_idx}] {msg.sender_name}: {msg.text}")
                if self._on_message:
                    await self._on_message(msg)
            except Exception as e:
                logger.error(f"Error handling channel message: {e}", exc_info=True)

        self._mc.subscribe(EventType.CONTACT_MSG_RECV, _handle_contact_msg)
        self._mc.subscribe(EventType.CHANNEL_MSG_RECV, _handle_channel_msg)

        await self._mc.start_auto_message_fetching()
        logger.info("Auto message fetching started.")

        while self._running:
            await asyncio.sleep(0.1)

    async def send_message(self, contact, text: str) -> bool:
        """
        Send a text message to a contact dict or pubkey string.
        Automatically chunks if the text exceeds 133 chars.
        Returns True if all chunks sent successfully.
        """
        from meshcore.events import EventType

        if not self._mc:
            raise RuntimeError("Not connected. Call connect() first.")

        dst = contact
        if isinstance(contact, dict):
            dst = contact

        chunks = chunk_message(text)
        logger.info(f"[TX] Sending {len(chunks)} chunk(s)...")

        for i, chunk in enumerate(chunks):
            try:
                result = await self._mc.commands.send_msg(dst, chunk)
                if result.type == EventType.ERROR:
                    logger.error(f"Failed to send chunk {i+1}: {result.payload}")
                    return False
                logger.debug(f"[TX] Chunk {i+1}/{len(chunks)} sent.")
                if i < len(chunks) - 1:
                    await asyncio.sleep(1.5)
            except Exception as e:
                logger.error(f"Error sending chunk {i+1}: {e}")
                return False

        return True

    async def send_channel_message(self, channel_idx: int, text: str) -> bool:
        """
        Send a text message to a channel by its index.
        Automatically chunks if the text exceeds 133 chars.
        Returns True if all chunks sent successfully.
        """
        from meshcore.events import EventType

        if not self._mc:
            raise RuntimeError("Not connected. Call connect() first.")

        chunks = chunk_message(text)
        logger.info(f"[TX CH{channel_idx}] Sending {len(chunks)} chunk(s)...")

        for i, chunk in enumerate(chunks):
            try:
                result = await self._mc.commands.send_channel_msg(channel_idx, chunk)
                if result.type == EventType.ERROR:
                    logger.error(f"Failed to send channel chunk {i+1}: {result.payload}")
                    return False
                logger.debug(f"[TX CH{channel_idx}] Chunk {i+1}/{len(chunks)} sent.")
                if i < len(chunks) - 1:
                    await asyncio.sleep(1.5)
            except Exception as e:
                logger.error(f"Error sending channel chunk {i+1}: {e}")
                return False

        return True

    async def send_to_id(self, node_id: str, text: str) -> bool:
        """Send a message to a node by its pubkey prefix hex string."""
        contact = self._contacts_cache.get(node_id)
        if not contact:
            await self._refresh_contacts()
            contact = self._contacts_cache.get(node_id)

        if contact:
            return await self.send_message(contact, text)

        logger.warning(f"Contact {node_id} not in cache, trying raw pubkey...")
        return await self.send_message(node_id, text)

    async def get_device_info(self) -> dict:
        """Get basic device info from the MeshCore radio."""
        if not self._mc:
            return {}
        try:
            result = await self._mc.commands.get_self()
            if hasattr(result, 'payload'):
                return {"self": str(result.payload)}
        except Exception:
            pass
        return {}

    async def disconnect(self):
        """Gracefully disconnect from the MeshCore device."""
        self._running = False
        if self._mc:
            try:
                self._mc.stop_auto_message_fetching()
            except Exception:
                pass
            try:
                await self._mc.disconnect()
                logger.info("Disconnected from MeshCore device.")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            self._mc = None
