"""
IoT / GPIO Handler Module
Parses ACTION:{} JSON from AI responses and executes physical device control.
Supports GPIO relay control on the gateway host (Raspberry Pi, Linux SBC, etc.)
"""

import json
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger("openclaw.iot")

# Pattern to detect ACTION JSON in AI responses
ACTION_PATTERN = re.compile(r'ACTION:\s*(\{[^}]+\})', re.IGNORECASE)

# GPIO pin mapping for common relay/device setups
DEFAULT_PIN_MAP = {
    "lights": 4,
    "basecamp_lights": 4,
    "relay1": 17,
    "relay2": 27,
    "relay3": 22,
    "relay4": 23,
    "fan": 24,
    "pump": 25,
    "siren": 18,
    "buzzer": 12,
}


class IoTHandler:
    """
    Handles IoT actions extracted from AI responses.
    Supports GPIO control via RPi.GPIO or lgpio, and extensible device types.
    """

    def __init__(self, pin_map: Optional[dict] = None, dry_run: bool = False):
        self.pin_map = pin_map or DEFAULT_PIN_MAP
        self.dry_run = dry_run
        self._gpio_available = False
        self._gpio = None
        self._initialized_pins: set = set()

        if not dry_run:
            self._init_gpio()

    def _init_gpio(self):
        """Try to initialize GPIO library."""
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            self._gpio = GPIO
            self._gpio_available = True
            logger.info("RPi.GPIO initialized (BCM mode).")
        except ImportError:
            try:
                import lgpio
                self._gpio = lgpio
                self._gpio_available = True
                logger.info("lgpio initialized.")
            except ImportError:
                logger.warning(
                    "No GPIO library available. IoT commands will be logged only."
                )

    def _setup_pin(self, pin: int):
        """Setup a GPIO pin as output if not already initialized."""
        if pin in self._initialized_pins:
            return
        if self._gpio_available and hasattr(self._gpio, 'setup'):
            self._gpio.setup(pin, self._gpio.OUT)
            self._initialized_pins.add(pin)

    def parse_action(self, ai_response: str) -> Tuple[Optional[dict], str]:
        """
        Extract ACTION JSON from AI response.
        Returns (action_dict, clean_response_text).
        """
        match = ACTION_PATTERN.search(ai_response)
        if not match:
            return None, ai_response

        try:
            action = json.loads(match.group(1))
            # Remove the ACTION line from the display text
            clean_text = ACTION_PATTERN.sub('', ai_response).strip()
            return action, clean_text
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse ACTION JSON: {e}")
            return None, ai_response

    def execute_action(self, action: dict) -> str:
        """
        Execute an IoT action and return a status message.
        Action format: {"device": "lights", "command": "on", "pin": 4}
        """
        device = action.get("device", "unknown")
        command = action.get("command", "").lower()
        pin = action.get("pin")

        # Resolve pin from device name if not specified
        if pin is None:
            pin = self.pin_map.get(device.lower())
        if pin is None:
            return f"Unknown device: {device}"

        if self.dry_run:
            logger.info(f"[DRY RUN] {device} pin {pin} -> {command}")
            return f"{device} {command} (simulated)"

        if not self._gpio_available:
            logger.info(f"[NO GPIO] {device} pin {pin} -> {command}")
            return f"{device} {command} (no GPIO)"

        try:
            self._setup_pin(pin)
            if command in ("on", "1", "high", "enable"):
                self._gpio.output(pin, self._gpio.HIGH)
                logger.info(f"GPIO {pin} ({device}) -> HIGH")
                return f"{device} turned ON"
            elif command in ("off", "0", "low", "disable"):
                self._gpio.output(pin, self._gpio.LOW)
                logger.info(f"GPIO {pin} ({device}) -> LOW")
                return f"{device} turned OFF"
            elif command == "toggle":
                current = self._gpio.input(pin)
                self._gpio.output(pin, not current)
                state = "OFF" if current else "ON"
                logger.info(f"GPIO {pin} ({device}) -> toggled to {state}")
                return f"{device} toggled {state}"
            else:
                return f"Unknown command: {command}"
        except Exception as e:
            logger.error(f"GPIO error on pin {pin}: {e}")
            return f"Error controlling {device}: {e}"

    def cleanup(self):
        """Cleanup GPIO on shutdown."""
        if self._gpio_available and hasattr(self._gpio, 'cleanup'):
            try:
                self._gpio.cleanup()
            except Exception:
                pass
