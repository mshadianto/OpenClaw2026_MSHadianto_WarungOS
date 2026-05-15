<div align="center">

# 🦞 WarungOS

**Autonomous Multi-Agent System for Indonesian UMKM Operations**

[![Telegram](https://img.shields.io/badge/Telegram-@mshadianto__co__bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/mshadianto_co_bot)
[![Claude](https://img.shields.io/badge/Powered_by-Claude_Sonnet_4.6-D97757)](https://www.anthropic.com)
[![DOKU](https://img.shields.io/badge/Payment-DOKU_MCP-FF1717)](https://www.doku.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

_Built solo in 12 hours for **RISTEK x Build Club OpenClaw Agenthon 2026**_

Track: Main Build + **Best Payment Use Case** (DOKU)

</div>

---

## 📌 The Problem

Indonesian UMKM owners (64M+ businesses, contributing 61% of GDP) face a daily operational treadmill:

- 🌅 Pre-dawn: stock-take warung manually
- 📞 Mid-morning: call 3-5 suppliers for quotes, negotiate prices
- 💸 Afternoon: manual bank transfers, manual receipt tracking
- 📲 Evening: WhatsApp every regular customer about restocked items
- 😴 Late night: reconcile sales, plan tomorrow

**This consumes 3-4 hours/day** — time better spent on growth, family, rest.

**WarungOS automates this entire loop in 90 seconds with a coordinated team of AI agents.**

---

## ✨ The Solution📸 1 photo of shelf → ⚡ 90 seconds → ✅ Full restock workflow complete
Zero human intervention

### The Agents

| Agent | Specialty | Tools Used | Decision Output |
|---|---|---|---|
| 🔍 **Inventory Sentinel** | Vision OCR + depletion forecasting | Claude Vision, SQLite | Critical items + 7-day forecast |
| 💼 **Procurement Negotiator** | Multi-criteria supplier selection + autonomous payment | LLM reasoning, supplier DB, **DOKU MCP** (35 tools) | Best supplier + DOKU Virtual Account |
| 📱 **Customer Concierge** | Personalized engagement in Bahasa Indonesia | Customer waitlist, contextual LLM | 1-of-1 messages per customer |

### What Makes WarungOS Different

- **Real autonomy** — agents make decisions, call tools, hand off to each other
- **Edge case mature** — handles supplier rejection (autonomous fallback) and payment failure (graceful escalation)
- **DOKU MCP native** — uses Indonesian payment MCP server for real B2B virtual account
- **Vision-first UX** — owner just takes a photo; agents do the rest
- **Bahasa Indonesia throughout** — agents speak natural local language
- **Local context aware** — references customer notes (catering Kamis, langganan Jumat, rumah makan)

---

## 🏗️ Architecture

```mermaidgraph TB
subgraph "User Interface"
TG[📱 Telegram Bot]
endsubgraph "Orchestration Layer"
    ORCH[🎭 Orchestrator]
endsubgraph "Agent Layer - Claude Sonnet 4.6"
    IS[🔍 Inventory Sentinel]
    PN[💼 Procurement Negotiator]
    CC[📱 Customer Concierge]
endsubgraph "Tool Layer"
    DB[(SQLite DB)]
    LLM[Sumopod LLM API]
    DOKU[💳 DOKU MCP Server]
    VIS[Claude Vision API]
endTG -->|photo or /restock| ORCH
ORCH --> IS
IS -->|critical items| PN
PN -->|PO + VA| CC
CC -->|notifications| TGIS <--> DB
IS <--> VIS
PN <--> DB
PN <--> LLM
PN <--> DOKU
CC <--> DB
CC <--> LLMstyle IS fill:#e1f5ff
style PN fill:#fff4e1
style CC fill:#e8f5e9
style DOKU fill:#ffe0e0
style ORCH fill:#f3e5f5

---

## 💳 DOKU MCP Integration — Best Payment Use Case

WarungOS uses DOKU MCP Server as the autonomous payment layer — not REST API calls, but native MCP tools that the agent invokes as part of its decision loop.

- **Live connection verified** — DOKU MCP returns 35 tools via tools/list
- **Agent-invoked**, not human-triggered — Procurement Negotiator calls create_virtual_account_payment autonomously
- **Multi-bank support** — tries BCA/BRI/BNI/Mandiri channels for resilience
- **Graceful fallback** — when DOKU sandbox VA service is intermittent, agent provides realistic VA for demo continuity
- **Schema-compliant** — uses toolRequest wrapper exactly per DOKU MCP spec
- **Failure escalation** — when payment fails across all channels, agent halts workflow and escalates with actionable recommendations

See `tools/doku_mcp.py` for the MCP client implementation.

---

## 🎬 Edge Case Demos (Autonomy Showcase)

### 1. Supplier Rejection — Autonomous Fallback Chain
Armed via `/scenario_reject`. Agent picks Supplier #1, gets rejected, autonomously excludes #1, picks Supplier #2 with new trade-off reasoning, workflow continues. Zero human intervention.

### 2. Payment Service Failure — Graceful Escalation
Armed via `/scenario_payfail`. DOKU MCP fails across all channels. Agent halts workflow, escalates to owner with 3 actionable recommendations + manual transfer amount. Customer Concierge NOT triggered — agent refuses to make promises it cannot keep.

### 3. Vision Quality Reject
Photo with poor lighting/focus. Vision agent classifies overall_quality=poor and asks user to re-upload with specific guidance.

---

## 🛠️ Tech Stack

| Layer | Choice |
|---|---|
| **LLM** | Claude Sonnet 4.6 via Sumopod |
| **Vision** | Claude Vision via Sumopod |
| **Payment** | DOKU MCP Server (35 tools) |
| **Interface** | Telegram Bot |
| **Database** | SQLite |
| **Runtime** | Python 3.12 + python-telegram-bot |
| **Infra** | Sumopod VPS Ubuntu 24.04 |

---

## 🚀 Quick Start

```bashgit clone https://github.com/mshadianto/OpenClaw2026_MSHadianto_WarungOS.git
cd OpenClaw2026_MSHadianto_WarungOSpython3 -m venv venv && source venv/bin/activate
pip install -r requirements.txtcp .env.example .env
nano .env  # fill credentialssqlite3 data/warungos.db < data/seed.sql
python3 bot.py

---

## 📁 Project Structurewarungos/
├── agents/
│   ├── inventory_sentinel.py     # Vision + forecasting
│   ├── procurement_negotiator.py # Multi-criteria + DOKU MCP
│   ├── customer_concierge.py     # Personalized engagement
│   └── orchestrator.py           # Workflow coordinator
├── tools/
│   ├── db.py                     # SQLite + audit log
│   ├── llm.py                    # Sumopod client (retry+backoff)
│   └── doku_mcp.py               # DOKU MCP JSON-RPC client
├── data/
│   ├── seed.sql                  # Demo data: Warung Bu Sari
│   └── warungos.db               # Runtime (gitignored)
├── bot.py                        # Telegram entry point
├── requirements.txt
└── README.md

---

## 📊 Telegram Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome + help |
| `/restock` | Trigger full autonomous workflow |
| `/status` | Show agent activity audit log |
| `/reset` | Restore demo data |
| `/scenarios` | List scenario flags |
| `/scenario_reject` | Arm supplier rejection scenario |
| `/scenario_payfail` | Arm payment failure scenario |
| `/scenario_clear` | Clear all scenario flags |
| 📸 Photo | Vision OCR + auto-trigger workflow |

---

## 🗺️ Roadmap

- WhatsApp Business API integration
- Voice command via Telegram voice notes
- Multi-warung tenant mode
- Real supplier API integrations (Indomarco, Sayurbox, TaniHub)
- Daily P&L automation
- Tax-ready bookkeeping (Indonesian VAT/PPN)
- Loan offer matching via cash flow data

---

## 🙋 About

Built solo by [M Shadianto](https://github.com/mshadianto) during 12-hour OpenClaw Agenthon 2026 build sprint.

---

## 📜 License

MIT
