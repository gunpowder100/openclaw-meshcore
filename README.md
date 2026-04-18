# MeshCore KI Integration

## ⚠️ Reliability warning: OpenClaw vs. Python-only MeshCore

**Do not use OpenClaw if you require reliability.**

OpenClaw is the most powerful add-on for MeshCore — **when you are physically sitting at the machine**. Nothing else adds as much capability.

**But:** If you need stability — especially for emergency services, remote operation, or unattended deployments — **use the Python-only version of MeshCore.**

The Python-only version relies entirely on proven, battle-tested architecture.

### Quick decision guide

| You are... | Use this |
|------------|----------|
| At the machine, want max features | OpenClaw ✅ |
| Emergency services / need stability | Python-only MeshCore ✅ |

**For critical infrastructure: choose Python-only.**
**AI-powered LoRa mesh gateway** — bridges [MeshCore](https://github.com/rpsreal/MeshCore) mesh networks with AI models for off-grid intelligent communication.

Send a text message from any MeshCore LoRa node → the gateway processes it through AI → you get an answer back over radio. No internet needed at the endpoint.

> **Two editions available:**
> - **Standalone** — slim Python scripts, direct Anthropic API, zero dependencies beyond an API key
> - **OpenClaw Edition** *(planned)* — MeshCore as a channel plugin for [OpenClaw](https://openclaw.ai), the open-source AI gateway

---

## Features

- **Dual AI Backend** — Claude Sonnet (remote, via Anthropic API) + Gemma 4 (local, via Ollama). Automatic failover between online and offline AI.
- **Off-Grid AI Chat** — Ask anything over LoRa radio. Hazmat identification, first aid protocols, weather, technical references — all without mobile coverage.
- **IoT Control** — Natural language commands like "turn on basecamp lights" get translated into GPIO actions on the gateway.
- **Message Chunking** — AI responses are automatically split into 133-character chunks (MeshCore limit) with `[n/N]` prefixes.
- **Privacy First** — No messages stored on disk. Log redaction enabled by default. Conversation context lives in RAM only, auto-purged after configurable timeout.
- **Access Control** — Open or allowlist-based DM policy, blocklist, optional message prefix gating.
- **Compact & Reliable** — Failover depends only on the API key. No cron jobs, no complex setup.
- **Duales KI-System** — Claude Sonnet (online, über Anthropic API) + Gemma 4 (lokal, über Ollama). Automatischer Wechsel zwischen Online- und Offline-KI — ohne Unterbrechung, ohne manuelle Umschaltung.
- **Offline-KI-Chat** — Fragen über LoRa-Funk, auch ohne Netzabdeckung. Gefahrstoffidentifikation, Erstversorgungsmaßnahmen, Wetterlage, technische Datenblätter — ideal für Tunneleinsätze, Katastrophenschutz und abgelegene Lagen.
- **Gerätesteuerung per Textnachricht** — Befehle wie „Basislagerbeleuchtung einschalten" werden automatisch in GPIO-Schaltbefehle übersetzt. Keine technischen Kenntnisse erforderlich.
- **Automatische Nachrichtenteilung** — KI-Antworten werden in 133-Zeichen-Blöcke aufgeteilt (MeshCore-Limit) mit Nummerierung `[1/3]`, `[2/3]`, `[3/3]`.
- **Datenschutz** — Keine Speicherung auf dem Datenträger. Protokoll-Anonymisierung standardmäßig aktiv. Gesprächskontext nur im Arbeitsspeicher, automatische Löschung nach konfigurierbarer Zeit.
- **Zugangskontrolle** — Offener oder listenbasierter Direktnachrichtenzugang, Sperrliste, optionale Präfix-Prüfung.
- **Kompakt & ausfallsicher** — Failover benötigt nur den API-Schlüssel. Keine Hintergrunddienste, keine komplexe Einrichtung.

## Architecture

### Standalone Edition

```
┌───────────────┐     LoRa 868 MHz     ┌─────────────────────┐
│  MeshCore Node│ ◄──────────────────► │  WIO Pro P1 Tracker │
│ (Handheld/App)│    MeshCore Protocol │ (USB Gateway Radio) │
└───────────────┘                      └─────────┬───────────┘
                                                 │
                                    USB Serial │ 115200 Baud
                                                 │
                                  ┌──────────────┴──────────────┐
                                  │      Server (Debian Linux)  │
                                  │                             │
                                  │  meshcore_client.py         │
                                  │  meshcore_service.py        │
                                  │  ai_backend.py              │
                                  │  iot_handler.py             │
                                  └──────┬──────────┬───────────┘
                                         │          │
                                    ▼          ▼
                          ┌───────────────┐  ┌─────────────────┐
                          │ Claude Sonnet │  │    Gemma 4      │
                          │(Anthropic API)│  │   (Ollama)      │
                          │ Remote/Primary│  │ Local/Fallback  │
                          └───────────────┘  └─────────────────┘
```

### OpenClaw Edition *(planned)*

```
┌───────────────┐                    ┌────────────────────┐
│  LoRa Mesh    │                    │  Chat Apps         │
│  (MeshCore)   │                    │  (WhatsApp, TG...) │
└───────┬───────┘                    └────────┬───────────┘
        │                                     │
        ▼                                     ▼
┌───────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway                       │
│                                                           │
│  MeshCore Channel Plugin  │  Chat Plugins  │  AI Router  │
│  Memory Manager           │  Context Engine              │
└──────────────┬────────────────────────┬───────────────────┘
               │                        │
          ▼                        ▼
   ┌───────────────┐       ┌─────────────────┐
   │ Claude Sonnet │       │    Gemma 4      │
   │   (Primary)   │       │  (Fallback)     │
   └───────────────┘       └─────────────────┘
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
  port: "auto"         # Serial port or "auto" for auto-detection
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
  require_prefix: ""    # e.g. "!ai " to only respond to prefixed messages

privacy:
  store_messages: false
  redact_logs: true
  disable_context: false
  context_timeout_minutes: 10
```

## Dual AI — Why Two Models?

| | Claude Sonnet (Primary) | Gemma 4 (Fallback) |
|---|---|---|
| **Location** | Remote (Anthropic API) | Local (Ollama) |
| **Internet** | Required | Not needed |
| **Knowledge** | Full reasoning, large context | Limited by storage & CPU |
| **Use case** | Complex queries, analysis | Basic Q&A, offline mode |
| **Trigger** | Default | Auto-failover when API unreachable |

> **Note:** Gemma 4 runs with limited knowledge scope due to server storage and CPU constraints — ideal for basic queries and predefined topics. The failover is fully automatic and depends only on the API key availability. No cron jobs or complex setup required.

## Mesh Commands

| Command | Description |
|---------|-------------|
| `!ai <text>` | Query the AI (if prefix is configured) |
| `!status` | Show system status |
| `!ping` | Test connectivity |

## Test Environment

| Component | Details |
|-----------|---------|
| Server | Hermes — Debian Linux, 192.168.178.73 |
| Gateway | WIO Pro P1 Tracker via USB (/dev/ttyACM0) |
| AI Primary | Claude Sonnet via Anthropic API (requires ANTHROPIC_API_KEY) |
| AI Fallback | Gemma 4 (gemma3:4b) via Ollama on localhost:11434 |
| LoRa Band | 868 MHz (EU) |
| Python | 3.13+ with asyncio |
| Packages | meshcore, httpx, pyyaml |

## Roadmap

- [x] Standalone Python integration
- [x] Dual AI failover (Claude + Gemma)
- [x] Channel message support
- [x] IoT/GPIO command parsing
- [ ] OpenClaw channel plugin integration
- [ ] Multi-channel bridging (LoRa ↔ WhatsApp/Telegram)
- [ ] Web dashboard

## License

MIT — see [LICENSE](LICENSE)

## Author

**Jonathan Salim** — Buergerfunkinitiative Essen-Kettwig
- GitHub: [gunpowder100](https://github.com/gunpowder100)
- Web: [jonathansalim.de](https://jonathansalim.de)
- Email: jonthan.salim@gmail.com

Copyright © 2026 Jonathan Salim. All rights reserved.
