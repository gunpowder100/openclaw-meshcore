"""
AI Backend Module
Handles routing between local Gemma 4 (Ollama) and remote Claude Sonnet (Anthropic API).
Auto-detects connectivity: tries remote first, falls back to local.
"""

import asyncio
import logging
import time
from typing import Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("openclaw.ai")

# System prompt optimized for mesh radio: short, direct responses
DEFAULT_SYSTEM_PROMPT = (
    "You are an AI assistant communicating over a LoRa mesh radio network. "
    "Your responses MUST be extremely concise — ideally under 120 characters. "
    "Use abbreviations where clear. No markdown, no formatting, no emojis. "
    "Plain text only. If asked a complex question, give the most useful short answer. "
    "If you need multiple sentences, keep each very short."
)

# GPIO/IoT control system prompt addition
IOT_SYSTEM_PROMPT = (
    "\nYou can also control IoT devices. If the user asks to control something "
    "(turn on/off lights, relays, sensors), respond with a JSON action line like: "
    'ACTION:{"device":"lights","command":"on","pin":4} followed by a short confirmation.'
)


@dataclass
class ConversationContext:
    """Per-sender conversation history for context-aware replies."""
    sender_id: str
    messages: list = field(default_factory=list)
    last_active: float = field(default_factory=time.time)
    max_history: int = 6  # Keep last 6 exchanges (small for mesh)

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        self._trim()
        self.last_active = time.time()

    def add_assistant_message(self, text: str):
        self.messages.append({"role": "assistant", "content": text})
        self._trim()

    def _trim(self):
        if len(self.messages) > self.max_history * 2:
            self.messages = self.messages[-(self.max_history * 2):]

    def get_messages(self) -> list:
        return list(self.messages)


class AIBackend:
    """
    AI backend with automatic failover:
    1. Try remote Claude Sonnet via Anthropic API
    2. Fall back to local Gemma 4 via Ollama
    """

    def __init__(
        self,
        ollama_url: str = "http://127.0.0.1:11434",
        ollama_model: str = "gemma3:4b",
        anthropic_api_key: Optional[str] = None,
        anthropic_model: str = "claude-sonnet-4-20250514",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        enable_iot: bool = True,
        prefer_local: bool = False,
        timeout: float = 30.0,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self.anthropic_api_key = anthropic_api_key
        self.anthropic_model = anthropic_model
        self.system_prompt = system_prompt
        if enable_iot:
            self.system_prompt += IOT_SYSTEM_PROMPT
        self.prefer_local = prefer_local
        self.timeout = timeout

        # Per-sender conversation contexts
        self._contexts: dict[str, ConversationContext] = {}

        # Connectivity state cache
        self._remote_available: Optional[bool] = None
        self._local_available: Optional[bool] = None
        self._last_check: float = 0
        self._check_interval: float = 60.0  # Re-check every 60s

    def _get_context(self, sender_id: str) -> ConversationContext:
        if sender_id not in self._contexts:
            self._contexts[sender_id] = ConversationContext(sender_id=sender_id)
        return self._contexts[sender_id]

    async def _check_remote(self) -> bool:
        """Check if Anthropic API is reachable."""
        if not self.anthropic_api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://api.anthropic.com/v1/messages",
                                         headers={"x-api-key": self.anthropic_api_key,
                                                   "anthropic-version": "2023-06-01"})
                # Even a 405 or 401 means the API is reachable
                return resp.status_code < 500
        except Exception:
            return False

    async def _check_local(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def _update_availability(self):
        """Refresh connectivity status if stale."""
        now = time.time()
        if now - self._last_check < self._check_interval:
            return

        self._remote_available, self._local_available = await asyncio.gather(
            self._check_remote(),
            self._check_local(),
        )
        self._last_check = now

        if self._remote_available:
            logger.info("Remote AI (Anthropic Sonnet) is available.")
        if self._local_available:
            logger.info("Local AI (Ollama/Gemma) is available.")
        if not self._remote_available and not self._local_available:
            logger.warning("No AI backend is reachable!")

    async def _query_anthropic(self, messages: list) -> str:
        """Query Claude Sonnet via Anthropic API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.anthropic_model,
                    "max_tokens": 200,  # Keep responses short for mesh
                    "system": self.system_prompt,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Extract text from response
            content = data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            return str(content)

    async def _query_ollama(self, messages: list) -> str:
        """Query Gemma 4 via Ollama API."""
        # Prepend system message for Ollama chat format
        ollama_messages = [{"role": "system", "content": self.system_prompt}]
        ollama_messages.extend(messages)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "num_predict": 200,  # Token limit for short responses
                        "temperature": 0.7,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    async def generate_reply(self, sender_id: str, user_text: str) -> str:
        """
        Generate an AI reply for a mesh message.
        Auto-selects backend based on connectivity.
        Returns the AI response text.
        """
        # Handle special commands
        lower = user_text.strip().lower()
        if lower in ("!ping", "ping"):
            return "pong"
        if lower in ("!status", "status"):
            await self._update_availability()
            remote = "ON" if self._remote_available else "OFF"
            local = "ON" if self._local_available else "OFF"
            return f"AI Status: Remote({remote}) Local({local})"
        if lower in ("!help", "help"):
            return (
                "Commands: !ping !status !local !remote. "
                "Or just chat naturally. IoT: 'turn on/off [device]'"
            )

        # Check for explicit model override
        force_local = lower.startswith("!local ")
        force_remote = lower.startswith("!remote ")
        if force_local:
            user_text = user_text[7:].strip()
        elif force_remote:
            user_text = user_text[8:].strip()

        # Update conversation context
        ctx = self._get_context(sender_id)
        ctx.add_user_message(user_text)
        messages = ctx.get_messages()

        # Auto-detect connectivity
        await self._update_availability()

        reply = None
        used_backend = None

        # Determine order of attempts
        if force_local:
            attempts = ["local"]
        elif force_remote:
            attempts = ["remote"]
        elif self.prefer_local:
            attempts = ["local", "remote"]
        else:
            attempts = ["remote", "local"]

        for backend in attempts:
            try:
                if backend == "remote" and self._remote_available:
                    logger.info(f"Querying Anthropic Sonnet for {sender_id}...")
                    reply = await self._query_anthropic(messages)
                    used_backend = "sonnet"
                    break
                elif backend == "local" and self._local_available:
                    logger.info(f"Querying Ollama/Gemma for {sender_id}...")
                    reply = await self._query_ollama(messages)
                    used_backend = "gemma"
                    break
            except Exception as e:
                logger.warning(f"Backend '{backend}' failed: {e}")
                # Mark as unavailable and try next
                if backend == "remote":
                    self._remote_available = False
                else:
                    self._local_available = False
                continue

        if reply is None:
            reply = "AI offline. No backend available. Try again later."
            logger.error("All AI backends failed.")
        else:
            logger.info(f"[{used_backend}] Reply: {reply[:80]}...")

        # Store assistant reply in context
        ctx.add_assistant_message(reply)

        return reply

    async def health_check(self) -> dict:
        """Return health status of all backends."""
        remote = await self._check_remote()
        local = await self._check_local()
        return {
            "remote_available": remote,
            "remote_model": self.anthropic_model if remote else None,
            "local_available": local,
            "local_model": self.ollama_model if local else None,
            "active_conversations": len(self._contexts),
        }
