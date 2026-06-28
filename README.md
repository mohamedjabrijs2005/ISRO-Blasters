# 🛰️ Astraeus NOC — Air-Gapped MPLS Predictive Copilot

> **ISRO Hackathon Winner** — 100% Offline AI for Mission-Critical Network Operations

![Network Health](https://img.shields.io/badge/Network-Operational-00e676?style=flat-square)
![AI Mode](https://img.shields.io/badge/AI-Air--Gapped%20%2F%20Offline-00b4ff?style=flat-square)
![Stack](https://img.shields.io/badge/Stack-FastAPI%20%2B%20Canvas%20%2B%20WebSocket-blueviolet?style=flat-square)

---

## What is Astraeus NOC?

Astraeus NOC is an **air-gapped, 100% offline AI Copilot** for ISRO's mission-critical MPLS ground station network. It monitors all Label Switched Paths (LSPs) across ISRO's global tracking stations in real-time, predicts network failures **5–15 minutes before they happen** using ML forecasting, and provides operators with actionable remediation via a natural language AI assistant.

**No internet. No cloud APIs. Zero external dependency.**

---

## Key Features

| Feature | Description |
|---|---|
| **Real-time Telemetry** | WebSocket-driven 2-second updates for all 8 LSPs and 6 ground station nodes |
| **ML Failure Prediction** | Holt-Winters time-series forecasting with anomaly Z-score detection |
| **Live Topology Map** | Animated Canvas-rendered MPLS network graph with real-time link health |
| **AI Copilot** | Local LLM (Ollama) + RAG knowledge base with offline rule-based fallback |
| **Anomaly Injection** | Demo scenarios: Solar flare, fiber cut, BGP oscillation, satellite burst |
| **Operator Actions** | One-click reroute with TE simulation and live utilization impact |

---

## Ground Station Network

| Node | Type | Location | Role |
|---|---|---|---|
| LER-BLR | LER | Bengaluru, India | Master Control Facility (40 Gbps) |
| LER-SDSC | LER | Sriharikota, India | Launch Control Center |
| LSR-HASAN | LSR | Hassan, Karnataka | Satellite TTC Operations |
| LSR-PB | LSR | Port Blair, Andaman | Real-time Tracking |
| LER-MU | LER | Mauritius | Deep Space Tracking |
| LER-BIAK | LER | Biak, Indonesia | Equatorial GEO Tracking |

---

## Quick Start

### Prerequisites
- Python 3.10+
- (Optional) [Ollama](https://ollama.ai) with `phi3:mini` or `mistral` for LLM mode

### Run (Windows)
```bat
# Double-click start.bat  OR  run in terminal:
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

### Run (Linux/macOS)
```bash
pip install fastapi "uvicorn[standard]" pydantic numpy
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

### Enable Local LLM (Optional)
```bash
# Install Ollama from https://ollama.ai (offline download)
ollama pull phi3:mini   # or mistral, llama3:8b
ollama serve            # runs on localhost:11434
# Then restart Astraeus — it auto-detects the model
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       BROWSER (Port 8000)                       │
│  ┌─────────────────────────────┐  ┌────────────────────────┐   │
│  │    MPLS Topology Canvas     │  │   AI Copilot Chat      │   │
│  │  D3-like animated graph     │  │  (Local LLM / RAG)     │   │
│  ├─────────────────────────────┤  ├────────────────────────┤   │
│  │  LSP Status Grid            │  │  Anomaly Scenarios     │   │
│  │  Real-time + Predicted KPIs │  │  One-click Rerouting   │   │
│  └─────────────────────────────┘  └────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ WebSocket (ws://localhost:8000/ws)
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI Backend (app.py)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐   │
│  │ simulator.py │  │ predictor.py│  │    assistant.py       │   │
│  │ MPLS Network │  │ Holt-Winters│  │ Ollama API / RAG /   │   │
│  │ Telemetry    │  │ + Z-score   │  │ Rule-based fallback   │   │
│  │ Simulator    │  │ Forecasting │  │                       │   │
│  └─────────────┘  └─────────────┘  └──────────────────────┘   │
│              2-second tick loop | WebSocket broadcast            │
└─────────────────────────────────────────────────────────────────┘
                    100% LOCAL — NO INTERNET REQUIRED
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | System health summary |
| GET | `/api/topology` | Network graph with telemetry |
| GET | `/api/telemetry` | Full snapshot + predictions |
| GET | `/api/lsp/{id}` | LSP detail + history + forecast |
| GET | `/api/predictions` | ML forecasts for all LSPs |
| GET | `/api/alerts` | Active predictive alerts |
| POST | `/api/chat` | AI Copilot query |
| POST | `/api/inject_anomaly` | Inject demo scenario |
| POST | `/api/reroute` | Apply TE reroute action |
| WS | `/ws` | Real-time bidirectional stream |

---

## Folder Structure

```
ISRO/
├── backend/
│   ├── __init__.py
│   ├── app.py          # FastAPI + WebSocket server
│   ├── simulator.py    # MPLS telemetry simulator
│   ├── predictor.py    # ML failure prediction engine
│   └── assistant.py    # LLM + RAG copilot
├── frontend/
│   ├── index.html      # Dashboard UI
│   ├── styles.css      # Premium dark glassmorphic CSS
│   └── app.js          # Canvas topology + charts + chat
├── requirements.txt
├── start.bat
└── README.md
```

---

## Demo Scenarios (for judging)

Click any scenario button in the sidebar to inject a live failure:

1. **Solar Flare Radio Interference** — RF degradation at Port Blair & Biak
2. **Satellite Downlink Burst** — LSP-101 congestion from launch telemetry
3. **Fiber Cut - East Coast** — Port Blair link goes DOWN, FRR triggers
4. **BGP Route Oscillation** — Latency spikes on Hassan MCF paths

---

## Resume Description

> **Astraeus NOC** — Air-Gapped AI Network Copilot for ISRO MPLS Infrastructure  
> Built a production-grade, 100% offline AI-powered NOC dashboard for ISRO's mission-critical MPLS ground station network. Features real-time WebSocket telemetry, Holt-Winters time-series ML forecasting (5–15 min ahead), animated Canvas topology map, and a natural language AI copilot using Local LLM (Ollama/phi3) with RAG over MPLS knowledge base. FastAPI backend with Python telemetry simulation of ISRO's 6 global tracking stations and 8 label switched paths. Zero cloud dependencies.

---

*Built for ISRO Hackathon 2026 — Astraeus NOC*
