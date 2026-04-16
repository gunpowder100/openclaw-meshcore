# OpenClaw MeshCore

**AI-powered LoRa mesh gateway** — bridges [MeshCore](https://github.com/rpsreal/MeshCore) mesh networks with AI models for off-grid intelligent communication.

Send a text message from any MeshCore LoRa node → the gateway processes it through AI → you get an answer back over radio. No internet needed at the endpoint.

## Features

- **Dual AI Backend** — Claude Sonnet (remote, via Anthropic API) + Gemma 4 (local, via Ollama). Automatic failover between online and offline AI.
- **Off-Grid AI Chat** — Ask anything over LoRa radio. Hazmat identification, first aid protocols, weather, technical references — all without mobile coverage.
- **IoT Control** — Natural language commands like "turn on basecamp lights" get translated into GPIO actions on the gateway.
- **Message Chunking** — AI responses are automatically split into 133-character chunks (MeshCore limit) with `[n/N]` prefixes.
- **Privacy First** — No messages stored on disk. Log redaction enabled by default. Conversation context lives in RAM only, auto-purged after configurable timeout.
- **Access Control** — Open or allowlist-based DM policy, blocklist, optional message prefix gating.

## Architecture

```
┌─────────────────┐     LoRa 864 MHz      ┌──────────────────────┐
│  MeshCore Node   │ ◄──────────────────► │  WIO Pro P1 Tracker  │
│  (Handheld/App)  │    MeshCore Protocol  │  (USB Gateway Radio) │
└─────────────────┘                        └──────────┬───────────┘
                                              USB Serial │ 115200 Baud
                                           ┌──────────┴───────────┐
                                           │   Hermes Server      │
                                           │   (Debian Linux)     │
                                           │                      │
                                           │  openclaw_meshcore.py│
                                           │  meshcore_client.py  │
                                           │  ai_backend.py       │
                                           │  iot_handler.py      │
                                           └───┬──────────┬───────┘
                                               │          │
                                   ┌───────────┘          └───────────┐
                                   ▼                                  ▼
                          ┌─────────────────┐              ┌─────────────────┐
                          │  Claude Sonnet  │              │   Gemma 4       │
                          │  (Anthropic API)│              │   (Ollama)      │
                          │  Remote/Primary │              │  Local/Fallback │
                          └─────────────────┘              └─────────────────┘
```

## Hardware

| Component | Details |
|-----------|---------|
| Gateway Radio | [Seeed WIO Pro P1 Tracker](https://www.seeedstudio.com/) |
| Interface | USB Serial, 115200 Baud, appears as `/dev/ttyACM0` |
| Server | Any Linux machine (Debian, Ubuntu, Raspberry Pi) |
| LoRa Nodes | Any MeshCore-compatible device |
| Cost | ~€50 per node |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/gunpowder100/openclaw-meshcore.git
cd openclaw-meshcore

# Run setup script (creates venv, installs deps, detects hardware)
chmod +x setup.sh
./setup.sh

# Configure
cp config.yaml config.local.yaml
# Edit config.local.yaml with your settings

# Set your Anthropic API key (optional, for remote AI)
export ANTHROPIC_API_KEY="sk-ant-..."

# Run
source .venv/bin/activate
python openclaw_meshcore.py
```

## Configuration

Edit `config.yaml` to customize:

```yaml
meshcore:
  port: "auto"          # Serial port or "auto" for auto-detection
  baud: 115200

ai:
  ollama_url: "http://127.0.0.1:11434"
  ollama_model: "gemma3:4b"
  anthropic_model: "claude-sonnet-4-20250514"
  prefer_local: false   # Set true to prefer local Gemma over remote Claude
  timeout: 30
  enable_iot: true

iot:
  enabled: true
  dry_run: true         # Set false when GPIO hardware is connected

access:
  dm_policy: "open"     # "open" or "allowlist"
  require_prefix: ""    # e.g. "\!ai " to only respond to prefixed messages

privacy:
  store_messages: false
  redact_logs: true
  disable_context: false
  context_timeout_minutes: 10
```

## Mesh Commands

| Command | Description |
|---------|-------------|
| `\!ping` | Check if gateway is alive |
| `\!status` | Show AI backend status (remote/local) |
| `\!help` | List available commands |
| `\!local <question>` | Force local AI (Gemma 4) |
| `\!remote <question>` | Force remote AI (Claude Sonnet) |

## Use Cases

- **Emergency Services (THW/Feuerwehr)** — Hazmat identification by UN number, first aid protocols, technical references — all without mobile coverage.
- **Disaster Response** — AI-assisted coordination when cell towers are down.
- **Amateur Radio (DARC)** — Demonstration of AI integration in off-grid communication networks.
- **Environmental Monitoring** — Sensor telemetry (GPS, temperature, air quality) fed into AI context.
- **IoT Control** — Voice-like natural language commands to control relays, lights, pumps over mesh radio.

## Project Structure

```
openclaw-meshcore/
├── openclaw_meshcore.py   # Main application — ties everything together
├── meshcore_client.py     # Async MeshCore serial client, message chunking
├── ai_backend.py          # Dual AI backend (Anthropic + Ollama) with failover
├── iot_handler.py         # GPIO/IoT action parser and executor
├── config.yaml            # Default configuration
├── requirements.txt       # Python dependencies
├── setup.sh               # Automated setup script
└── __init__.py
```

## Dependencies

- Python 3.10+
- [meshcore](https://pypi.org/project/meshcore/) — MeshCore Python SDK
- [httpx](https://www.python-httpx.org/) — Async HTTP client
- [PyYAML](https://pyyaml.org/) — Configuration parsing
- Optional: RPi.GPIO or lgpio for hardware GPIO control

## Privacy & Security

- **No disk storage** — Messages and mesh data are never written to disk.
- **Log redaction** — Message content is suppressed in logs by default (`redact_logs: true`).
- **RAM-only context** — Conversation history lives in memory only, auto-purged after configurable timeout.
- **No telemetry** — The gateway does not phone home or collect analytics.

## Inspired By

- [MeshClaw](https://github.com/Seeed-Solution/MeshClaw) — AI integration for Meshtastic (TypeScript). OpenClaw MeshCore adapts this concept for the MeshCore protocol using Python.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome\! Open an issue or submit a pull request.

---

*Built by the MeshCore Community — 73\!*
