"""
Astraeus NOC — FastAPI Backend
Air-Gapped Predictive MPLS Copilot for ISRO Ground Network Operations
100% Offline — No internet dependencies
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.simulator import simulator, ANOMALY_SCENARIOS
from backend.predictor import predictor
from backend.assistant import copilot
from backend.missions import oam_monitor, mission_monitor

# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Astraeus NOC — ISRO MPLS Predictive Copilot",
    description="Air-gapped AI copilot for ISRO MPLS network operations",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# ─── Serverless Simulation Logic ──────────────────────────────────────────────

def tick_simulation():
    """Advance the simulation state by one tick for serverless environments."""
    simulator.tick_update()
    snap = simulator.get_snapshot()
    preds = predictor.analyze_all(snap["history"])
    oam_monitor.tick(snap.get("active_anomalies", []))
    mission_monitor.tick()
    return snap, preds



# ─── Frontend Route ────────────────────────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ─── REST API ─────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    """Current network snapshot"""
    snap, preds = tick_simulation()
    return {
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
        "network_health": preds.get("network_health", "unknown"),
        "network_risk_score": preds.get("network_risk_score", 0),
        "active_alerts": len(preds.get("active_alerts", [])),
        "nodes_up": sum(1 for n in snap["nodes"].values() if n.get("status") == "UP"),
        "total_nodes": len(snap["nodes"]),
        "lsps_up": sum(1 for l in snap["lsps"] if l.get("status") == "UP"),
        "total_lsps": len(snap["lsps"]),
        "llm_available": copilot.llm_available,
        "llm_model": copilot.llm.model if copilot.llm_available else "rule-based"
    }


@app.get("/api/topology")
async def api_topology():
    """Network topology with real-time telemetry"""
    snap, preds = tick_simulation()
    return {
        "nodes": snap["nodes"],
        "lsps": snap["lsps"],
        "predictions": {
            k: {"risk_score": v["risk_score"], "risk_level": v["risk_level"]}
            for k, v in preds.get("lsp_predictions", {}).items()
        }
    }


@app.get("/api/telemetry")
async def api_telemetry():
    """Full telemetry snapshot with predictions"""
    snap, preds = tick_simulation()
    return {"snapshot": snap, "predictions": preds}


@app.get("/api/lsp/{lsp_id}")
async def api_lsp_detail(lsp_id: str):
    """Detailed info for a specific LSP"""
    snap = simulator.get_snapshot()
    lsp = next((l for l in snap["lsps"] if l["id"] == lsp_id), None)
    if not lsp:
        raise HTTPException(404, f"LSP {lsp_id} not found")

    history = simulator.get_lsp_history(lsp_id, 60)
    preds = predictor.models[lsp_id].analyze(history) if lsp_id in predictor.models else {}
    return {
        "lsp": lsp,
        "history": history,
        "prediction": preds,
        "label_stack": {
            "in_label":  lsp.get("label_in"),
            "out_label": lsp.get("label_out"),
            "type":      lsp.get("type"),
            "priority":  lsp.get("priority"),
        }
    }


@app.get("/api/predictions")
async def api_predictions():
    """Latest ML predictions for all LSPs"""
    snap = simulator.get_snapshot()
    preds = predictor.analyze_all(snap["history"])
    return preds


@app.get("/api/alerts")
async def api_alerts():
    """Active network alerts"""
    snap = simulator.get_snapshot()
    preds = prediction_cache if prediction_cache else predictor.analyze_all(snap["history"])
    return {
        "alerts": preds.get("active_alerts", []),
        "total": preds.get("total_alerts", 0),
        "network_health": preds.get("network_health"),
        "anomalies": snap.get("active_anomalies", [])
    }


class ChatRequest(BaseModel):
    query: str


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """AI Copilot chat endpoint"""
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    snap  = simulator.get_snapshot()
    preds = predictor.analyze_all(snap["history"])
    result = copilot.query(req.query, snap, preds)
    return result


class AnomalyRequest(BaseModel):
    scenario: str


@app.post("/api/inject_anomaly")
async def api_inject_anomaly(req: AnomalyRequest):
    """Manually inject an anomaly scenario (for demo)"""
    result = simulator.inject_anomaly(req.scenario)
    if result:
        return {"success": True, "scenario": result["name"], "duration_s": result["duration_s"]}
    raise HTTPException(404, f"Scenario '{req.scenario}' not found")


@app.get("/api/scenarios")
async def api_scenarios():
    """List available demo anomaly scenarios"""
    return {
        "scenarios": [
            {"name": s["name"], "description": s["description"]}
            for s in ANOMALY_SCENARIOS
        ]
    }


class RerouteRequest(BaseModel):
    lsp_id: str
    via_node: str


@app.post("/api/reroute")
async def api_reroute(req: RerouteRequest):
    """Accept and apply an AI-suggested reroute action"""
    result = simulator.accept_reroute(req.lsp_id, req.via_node)
    return result


@app.get("/api/missions")
async def api_missions():
    """Active ISRO missions and telemetry context"""
    return {
        "missions": mission_monitor.get_all(),
        "active_count": len(mission_monitor.get_active())
    }


@app.get("/api/oam")
async def api_oam():
    """Recent OAM events (CCM, loopback, AIS, BFD)"""
    return {
        "events": oam_monitor.get_recent(30),
        "stats": oam_monitor.get_stats()
    }


@app.get("/api/heatmap")
async def api_heatmap():
    """LSP utilization heatmap data (time x LSP grid)"""
    snap, _ = tick_simulation()
    history = snap["history"]
    lsp_ids = [lsp["id"] for lsp in snap["lsps"]]
    # Build 20-point x N-LSP grid
    grid = {}
    for lsp_id in lsp_ids:
        hist = history.get(lsp_id, [])[-20:]
        grid[lsp_id] = [round(h.get("utilization", 0) * 100, 1) for h in hist]
    return {"lsp_ids": lsp_ids, "grid": grid, "points": 20}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
