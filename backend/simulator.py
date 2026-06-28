"""
MPLS Telemetry Simulator for ISRO Ground Station Network
Generates realistic SNMP/NetFlow-style telemetry with anomaly injection
"""

import random
import time
import math
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

# ─── ISRO Ground Station Topology ─────────────────────────────────────────────

NODES = {
    "LER-BLR": {
        "id": "LER-BLR",
        "label": "Bengaluru HQ",
        "type": "LER",
        "location": "Bengaluru, India",
        "lat": 12.9716, "lon": 77.5946,
        "role": "Master Control Facility",
        "capacity_gbps": 40
    },
    "LER-SDSC": {
        "id": "LER-SDSC",
        "label": "Sriharikota",
        "type": "LER",
        "location": "Sriharikota, India",
        "lat": 13.7200, "lon": 80.2300,
        "role": "Launch Control Center",
        "capacity_gbps": 10
    },
    "LSR-PB": {
        "id": "LSR-PB",
        "label": "Port Blair",
        "type": "LSR",
        "location": "Port Blair, Andaman",
        "lat": 11.6234, "lon": 92.7265,
        "role": "Tracking Station",
        "capacity_gbps": 5
    },
    "LER-MU": {
        "id": "LER-MU",
        "label": "Mauritius",
        "type": "LER",
        "location": "Mauritius",
        "lat": -20.1609, "lon": 57.4977,
        "role": "Deep Space Tracking",
        "capacity_gbps": 5
    },
    "LER-BIAK": {
        "id": "LER-BIAK",
        "label": "Biak Station",
        "type": "LER",
        "location": "Biak, Indonesia",
        "lat": -1.1767, "lon": 136.1069,
        "role": "Equatorial Tracking",
        "capacity_gbps": 5
    },
    "LSR-HASAN": {
        "id": "LSR-HASAN",
        "label": "Hassan MCF",
        "type": "LSR",
        "location": "Hassan, Karnataka",
        "lat": 13.0068, "lon": 76.0996,
        "role": "Satellite Control",
        "capacity_gbps": 20
    }
}

# LSP Definitions: Label Switched Paths
LSP_DEFINITIONS = [
    {"id": "LSP-101", "src": "LER-SDSC", "dst": "LER-BLR",  "label_in": 1001, "label_out": 2001, "priority": "critical", "type": "Telemetry"},
    {"id": "LSP-102", "src": "LER-BLR",  "dst": "LSR-HASAN", "label_in": 1002, "label_out": 2002, "priority": "high",     "type": "Command"},
    {"id": "LSP-103", "src": "LSR-PB",   "dst": "LER-BLR",  "label_in": 1003, "label_out": 2003, "priority": "critical", "type": "Tracking"},
    {"id": "LSP-104", "src": "LER-MU",   "dst": "LER-BLR",  "label_in": 1004, "label_out": 2004, "priority": "high",     "type": "DeepSpace"},
    {"id": "LSP-105", "src": "LER-BIAK", "dst": "LER-BLR",  "label_in": 1005, "label_out": 2005, "priority": "medium",   "type": "Tracking"},
    {"id": "LSP-106", "src": "LER-SDSC", "dst": "LSR-HASAN","label_in": 1006, "label_out": 2006, "priority": "high",     "type": "Command"},
    {"id": "LSP-107", "src": "LER-BLR",  "dst": "LSR-PB",   "label_in": 1007, "label_out": 2007, "priority": "medium",   "type": "Backup"},
    {"id": "LSP-108", "src": "LER-BLR",  "dst": "LER-MU",   "label_in": 1008, "label_out": 2008, "priority": "medium",   "type": "Backup"},
]

# Anomaly Scenarios
ANOMALY_SCENARIOS = [
    {
        "name": "Solar Flare Radio Interference",
        "description": "Ionospheric disturbance affecting RF links at equatorial stations",
        "affected_nodes": ["LSR-PB", "LER-BIAK"],
        "metric": "packet_loss",
        "severity": 0.15,
        "duration_s": 120
    },
    {
        "name": "Satellite Downlink Burst",
        "description": "Heavy telemetry from PSLV-C59 launch causing traffic surge on LSP-101",
        "affected_lsps": ["LSP-101"],
        "metric": "utilization",
        "severity": 0.92,
        "duration_s": 90
    },
    {
        "name": "Fiber Cut - East Coast",
        "description": "Undersea cable disruption affecting Port Blair–Bengaluru link",
        "affected_lsps": ["LSP-103"],
        "metric": "link_down",
        "severity": 1.0,
        "duration_s": 60
    },
    {
        "name": "BGP Route Oscillation",
        "description": "Routing instability causing latency spikes on Hassan MCF path",
        "affected_lsps": ["LSP-102", "LSP-106"],
        "metric": "latency",
        "severity": 0.6,
        "duration_s": 75
    }
]


class MPLSSimulator:
    def __init__(self):
        self.nodes = {k: dict(v) for k, v in NODES.items()}
        self.lsps = [dict(lsp) for lsp in LSP_DEFINITIONS]
        self.telemetry_history: Dict[str, List] = {lsp["id"]: [] for lsp in self.lsps}
        self.node_history: Dict[str, List] = {nid: [] for nid in NODES}
        self.active_anomalies: List[dict] = []
        self.anomaly_timer = 0
        self.tick = 0
        self._lock = threading.Lock()

        # Initialize baseline states
        self._init_states()

    def _init_states(self):
        """Initialize smooth baseline telemetry states per LSP"""
        for lsp in self.lsps:
            lsp["utilization"] = random.uniform(0.25, 0.55)
            lsp["latency_ms"] = random.uniform(8, 35)
            lsp["packet_loss"] = random.uniform(0.0, 0.005)
            lsp["jitter_ms"] = random.uniform(0.5, 3.0)
            lsp["bandwidth_gbps"] = random.uniform(0.5, 2.0)
            lsp["status"] = "UP"
            lsp["health"] = "nominal"
            # Populate history with 60 initial points
            for i in range(60):
                self.telemetry_history[lsp["id"]].append({
                    "ts": (datetime.utcnow() - timedelta(seconds=(60 - i) * 2)).isoformat(),
                    "utilization": lsp["utilization"] + random.gauss(0, 0.03),
                    "latency_ms": lsp["latency_ms"] + random.gauss(0, 1.5),
                    "packet_loss": max(0, lsp["packet_loss"] + random.gauss(0, 0.001)),
                })

        for node_id, node in self.nodes.items():
            node["cpu_pct"] = random.uniform(15, 40)
            node["mem_pct"] = random.uniform(30, 60)
            node["temp_c"] = random.uniform(32, 52)
            node["status"] = "UP"
            node["label_table_size"] = random.randint(850, 1200)

    def _apply_anomaly(self, lsp: dict):
        """Apply active anomaly effects to a given LSP"""
        for anomaly in self.active_anomalies:
            if "affected_lsps" in anomaly and lsp["id"] in anomaly["affected_lsps"]:
                if anomaly["metric"] == "utilization":
                    lsp["utilization"] = min(0.98, lsp["utilization"] * (1 + anomaly["severity"] * 0.5))
                elif anomaly["metric"] == "latency":
                    lsp["latency_ms"] *= (1 + anomaly["severity"])
                elif anomaly["metric"] == "link_down":
                    lsp["status"] = "DOWN"
                    lsp["utilization"] = 0
            if "affected_nodes" in anomaly:
                src_node = lsp["src"]
                if src_node in anomaly["affected_nodes"] and anomaly["metric"] == "packet_loss":
                    lsp["packet_loss"] = min(0.5, lsp["packet_loss"] + anomaly["severity"])

    def _random_walk(self, value: float, target_center: float, std: float,
                     lo: float, hi: float, mean_reversion: float = 0.05) -> float:
        """Ornstein-Uhlenbeck-like mean-reverting random walk"""
        drift = mean_reversion * (target_center - value)
        noise = random.gauss(0, std)
        return max(lo, min(hi, value + drift + noise))

    def _maybe_inject_anomaly(self):
        """Randomly inject realistic MPLS anomaly scenarios"""
        self.anomaly_timer -= 1
        if self.anomaly_timer <= 0 and len(self.active_anomalies) == 0:
            if random.random() < 0.03:  # ~3% chance per tick
                scenario = random.choice(ANOMALY_SCENARIOS)
                anomaly = dict(scenario)
                anomaly["start_tick"] = self.tick
                anomaly["end_tick"] = self.tick + int(anomaly["duration_s"] / 2)
                self.active_anomalies.append(anomaly)
                self.anomaly_timer = anomaly["end_tick"] - self.tick + 30

        # Expire old anomalies
        self.active_anomalies = [
            a for a in self.active_anomalies if a.get("end_tick", 0) > self.tick
        ]

    def tick_update(self):
        """Advance simulation by one tick (called every ~2 seconds)"""
        with self._lock:
            self.tick += 1
            self._maybe_inject_anomaly()

            # Add time-of-day variation (ISRO peak: 06:00–14:00 IST for launches)
            hour = datetime.utcnow().hour + 5.5  # IST offset
            peak_factor = 1.0 + 0.3 * math.exp(-((hour - 10) ** 2) / 18)

            for lsp in self.lsps:
                if lsp["status"] == "DOWN":
                    lsp["status"] = "DOWN"
                    # Recovery after anomaly expires
                    still_down = any(
                        "link_down" in a.get("metric", "") and lsp["id"] in a.get("affected_lsps", [])
                        for a in self.active_anomalies
                    )
                    if not still_down:
                        lsp["status"] = "UP"
                    continue

                center_util = 0.4 * peak_factor
                lsp["utilization"] = self._random_walk(lsp["utilization"], center_util, 0.025, 0.01, 0.99)
                lsp["latency_ms"] = self._random_walk(lsp["latency_ms"], 20, 1.2, 3, 150)
                lsp["packet_loss"] = self._random_walk(lsp["packet_loss"], 0.001, 0.0008, 0, 0.3)
                lsp["jitter_ms"] = self._random_walk(lsp["jitter_ms"], 1.5, 0.2, 0.1, 15)

                self._apply_anomaly(lsp)

                # Determine health status
                if lsp["utilization"] > 0.85 or lsp["packet_loss"] > 0.05 or lsp["latency_ms"] > 80:
                    lsp["health"] = "critical"
                elif lsp["utilization"] > 0.70 or lsp["packet_loss"] > 0.02 or lsp["latency_ms"] > 50:
                    lsp["health"] = "warning"
                else:
                    lsp["health"] = "nominal"

                # Append to history (keep last 120 points)
                self.telemetry_history[lsp["id"]].append({
                    "ts": datetime.utcnow().isoformat(),
                    "utilization": round(lsp["utilization"], 4),
                    "latency_ms": round(lsp["latency_ms"], 2),
                    "packet_loss": round(lsp["packet_loss"], 5),
                })
                if len(self.telemetry_history[lsp["id"]]) > 120:
                    self.telemetry_history[lsp["id"]].pop(0)

            # Update node metrics
            for node_id, node in self.nodes.items():
                node["cpu_pct"] = self._random_walk(node["cpu_pct"], 35, 2.5, 5, 95)
                node["mem_pct"] = self._random_walk(node["mem_pct"], 55, 1.5, 20, 95)
                node["temp_c"] = self._random_walk(node["temp_c"], 45, 0.8, 25, 85)
                node["label_table_size"] = int(self._random_walk(node["label_table_size"], 1000, 15, 500, 2000))

    def get_snapshot(self) -> dict:
        """Return complete current state snapshot"""
        with self._lock:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "tick": self.tick,
                "nodes": {k: dict(v) for k, v in self.nodes.items()},
                "lsps": [dict(lsp) for lsp in self.lsps],
                "active_anomalies": [
                    {"name": a["name"], "description": a["description"]}
                    for a in self.active_anomalies
                ],
                "history": {
                    k: list(v[-60:]) for k, v in self.telemetry_history.items()
                }
            }

    def get_lsp_history(self, lsp_id: str, points: int = 60) -> List[dict]:
        with self._lock:
            return list(self.telemetry_history.get(lsp_id, [])[-points:])

    def inject_anomaly(self, scenario_name: str) -> Optional[dict]:
        """Manually inject a named anomaly scenario"""
        for scenario in ANOMALY_SCENARIOS:
            if scenario["name"].lower() == scenario_name.lower():
                anomaly = dict(scenario)
                anomaly["start_tick"] = self.tick
                anomaly["end_tick"] = self.tick + int(anomaly["duration_s"] / 2)
                with self._lock:
                    self.active_anomalies.append(anomaly)
                return anomaly
        return None

    def accept_reroute(self, lsp_id: str, via_node: str) -> dict:
        """Simulate traffic engineering reroute action"""
        with self._lock:
            for lsp in self.lsps:
                if lsp["id"] == lsp_id:
                    old_util = lsp["utilization"]
                    lsp["utilization"] = max(0.1, old_util * 0.6)
                    lsp["latency_ms"] = lsp["latency_ms"] * 0.8
                    lsp["packet_loss"] = 0.0
                    lsp["health"] = "nominal"
                    lsp["rerouted_via"] = via_node
                    return {
                        "success": True,
                        "lsp_id": lsp_id,
                        "old_utilization": old_util,
                        "new_utilization": lsp["utilization"],
                        "via": via_node,
                        "message": f"Traffic rerouted via {via_node}. Utilization dropped from {old_util:.0%} to {lsp['utilization']:.0%}."
                    }
        return {"success": False, "message": "LSP not found"}


# Singleton instance
simulator = MPLSSimulator()
