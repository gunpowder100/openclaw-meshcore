#!/usr/bin/env python3
"""
OpenClaw MeshCore Integration
Bridges MeshCore LoRa mesh network with AI models.
"""

import argparse
import asyncio
import logging
import os
import signal
import time as _time
from pathlib import Path

import yaml

from meshcore_client import MeshCoreClient, MeshMessage
from ai_backend import AIBackend
from iot_handler import IoTHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("openclaw")

DEFAULT_CONFIG = {
    "meshcore": {
        "port": "/dev/ttyACM0",
        "baud": 115200,
        "debug": False,
    },
    "ai": {
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "gemma3:4b",
        "anthropic_api_key": "",
        "anthropic_model": "claude-sonnet-4-20250514",
        "prefer_local": False,
        "timeout": 30,
        "system_prompt": "",
        "enable_iot": True,
    },
    "iot": {
        "enabled": True,
        "dry_run": False,
        "pin_map": {},
    },
    "access": {
        "dm_policy": "open",
        "allowlist": [],
        "blocked": [],
        "require_prefix": "",
    },
    "privacy": {
        "store_messages": False,
        "redact_logs": True,
        "disable_context": False,
        "context_timeout_minutes": 10,
    },
}


def load_config(path=None):
    config = dict(DEFAULT_CONFIG)
    if path and Path(path).exists():
        with open(path) as f:
            user_cfg = yaml.safe_load(f) or {}
        for section in config:
            if section in user_cfg and isinstance(user_cfg[section], dict):
                config[section].update(user_cfg[section])
        logger.info(f"Config loaded from {path}")
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key:
        config["ai"]["anthropic_api_key"] = env_key
    env_ollama = os.environ.get("OLLAMA_URL", "")
    if env_ollama:
        config["ai"]["ollama_url"] = env_ollama
    env_port = os.environ.get("MESHCORE_PORT", "")
    if env_port:
        config["meshcore"]["port"] = env_port
    return config


def detect_serial_port():
    import glob
    candidates = []
    for pattern in ["/dev/ttyACM*", "/dev/ttyUSB*"]:
        candidates.extend(glob.glob(pattern))
    if not candidates:
        logger.warning("No serial ports found. Using default /dev/ttyACM0")
        return "/dev/ttyACM0"
    acm = [p for p in candidates if "ACM" in p]
    if acm:
        port = sorted(acm)[0]
        logger.info(f"Auto-detected MeshCore port: {port}")
        return port
    port = sorted(candidates)[0]
    logger.info(f"Auto-detected serial port: {port}")
    return port


class OpenClawMeshCore:
    def __init__(self, config):
        self.config = config
        self.mesh = None
        self.ai = None
        self.iot = None
        self._shutdown = False

    async def setup(self):
        mc_cfg = self.config["meshcore"]
        ai_cfg = self.config["ai"]
        iot_cfg = self.config["iot"]
        access_cfg = self.config["access"]
        privacy_cfg = self.config.get("privacy", {})

        self.dm_policy = access_cfg.get("dm_policy", "open")
        self.allowlist = set(access_cfg.get("allowlist", []))
        self.blocked = set(access_cfg.get("blocked", []))
        self.require_prefix = access_cfg.get("require_prefix", "")
        self.redact_logs = privacy_cfg.get("redact_logs", True)
        self.disable_context = privacy_cfg.get("disable_context", False)
        self.context_timeout = privacy_cfg.get("context_timeout_minutes", 10) * 60

        port = mc_cfg["port"]
        if port == "auto":
            port = detect_serial_port()

        self.mesh = MeshCoreClient(
            port=port,
            baud=mc_cfg.get("baud", 115200),
            debug=mc_cfg.get("debug", False),
            redact_logs=self.redact_logs,
        )

        system_prompt = ai_cfg.get("system_prompt", "") or None
        self.ai = AIBackend(
            ollama_url=ai_cfg.get("ollama_url", "http://127.0.0.1:11434"),
            ollama_model=ai_cfg.get("ollama_model", "gemma3:4b"),
            anthropic_api_key=ai_cfg.get("anthropic_api_key", ""),
            anthropic_model=ai_cfg.get("anthropic_model", "claude-sonnet-4-20250514"),
            system_prompt=system_prompt or "",
            enable_iot=ai_cfg.get("enable_iot", True),
            prefer_local=ai_cfg.get("prefer_local", False),
            timeout=ai_cfg.get("timeout", 30),
        )
        if not system_prompt:
            from ai_backend import DEFAULT_SYSTEM_PROMPT, IOT_SYSTEM_PROMPT
            self.ai.system_prompt = DEFAULT_SYSTEM_PROMPT
            if ai_cfg.get("enable_iot", True):
                self.ai.system_prompt += IOT_SYSTEM_PROMPT

        self.iot = IoTHandler(
            pin_map=iot_cfg.get("pin_map") or None,
            dry_run=iot_cfg.get("dry_run", False),
        )

        logger.info("OpenClaw MeshCore initialized.")
        logger.info(f"  Port: {port} | Redact: {self.redact_logs} | Context timeout: {self.context_timeout}s")

    def _check_access(self, msg):
        if msg.sender_id in self.blocked:
            return False
        if self.require_prefix:
            if not msg.text.lower().startswith(self.require_prefix.lower()):
                return False
        if self.dm_policy == "allowlist":
            if msg.sender_id not in self.allowlist:
                return False
        return True

    async def _handle_message(self, msg):
        if not self._check_access(msg):
            return

        text = msg.text
        if self.require_prefix and text.lower().startswith(self.require_prefix.lower()):
            text = text[len(self.require_prefix):].strip()
        if not text:
            return

        if self.redact_logs:
            logger.info(f"Processing message from {msg.sender_name}")
        else:
            logger.info(f"Processing message from {msg.sender_name}: {text}")

        # Privacy: purge stale contexts
        if self.context_timeout > 0 and hasattr(self.ai, '_contexts'):
            now = _time.time()
            stale = [k for k, v in self.ai._contexts.items()
                     if now - v.last_active > self.context_timeout]
            for k in stale:
                del self.ai._contexts[k]

        try:
            reply = await self.ai.generate_reply(msg.sender_id, text)
            if self.disable_context:
                self.ai._contexts.pop(msg.sender_id, None)

            if self.config["iot"].get("enabled", True):
                action, clean_reply = self.iot.parse_action(reply)
                if action:
                    iot_result = self.iot.execute_action(action)
                    reply = f"{clean_reply} [{iot_result}]" if clean_reply else iot_result

            if msg.contact:
                success = await self.mesh.send_message(msg.contact, reply)
            else:
                success = await self.mesh.send_to_id(msg.sender_id, reply)

            if success:
                logger.info(f"Reply sent to {msg.sender_name}")
            else:
                logger.error(f"Failed to send reply to {msg.sender_name}")

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            try:
                if msg.contact:
                    await self.mesh.send_message(msg.contact, f"Error: {str(e)[:100]}")
            except Exception:
                pass

    async def run(self):
        await self.setup()
        await self.mesh.connect()
        self.mesh.on_message(self._handle_message)

        health = await self.ai.health_check()
        logger.info(f"AI Health: {health}")

        print("\n" + "=" * 60)
        print("  OpenClaw MeshCore Integration")
        print("  AI-powered LoRa mesh gateway")
        print("=" * 60)
        print(f"  Remote AI: {'ONLINE' if health['remote_available'] else 'OFFLINE'}")
        print(f"  Local AI:  {'ONLINE' if health['local_available'] else 'OFFLINE'}")
        print(f"  Privacy:   redact_logs={self.redact_logs} store=OFF")
        print("=" * 60)
        print("  Listening for mesh messages... (Ctrl+C to stop)")
        print("=" * 60 + "\n")

        try:
            await self.mesh.start_listening()
        except asyncio.CancelledError:
            logger.info("Shutting down...")
        finally:
            await self.shutdown()

    async def shutdown(self):
        if self._shutdown:
            return
        self._shutdown = True
        logger.info("Shutting down OpenClaw MeshCore...")
        if self.mesh:
            await self.mesh.disconnect()
        if self.iot:
            self.iot.cleanup()
        logger.info("Shutdown complete.")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw MeshCore")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--port", "-p", default=None)
    parser.add_argument("--prefer-local", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    config = load_config(args.config)
    if args.port:
        config["meshcore"]["port"] = args.port
    if args.prefer_local:
        config["ai"]["prefer_local"] = True
    if args.dry_run:
        config["iot"]["dry_run"] = True
    if args.debug:
        config["meshcore"]["debug"] = True

    app = OpenClawMeshCore(config)
    loop = asyncio.new_event_loop()

    def signal_handler():
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(app.run())
    except KeyboardInterrupt:
        loop.run_until_complete(app.shutdown())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
