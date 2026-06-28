"""
ISRO Mission Control Data & OAM Events Simulator
Adds mission context + real-time OAM fault monitoring to the copilot
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict

# ─── ISRO Active Missions ──────────────────────────────────────────────────────

MISSIONS = [
    {
        "id": "PSLV-C60",
        "name": "PSLV-C60 / SpaDeX",
        "type": "PSLV",
        "status": "active",
        "phase": "Telemetry Downlink",
        "orbit": "LEO 475km",
        "primary_lsp": "LSP-101",
        "tracking_stations": ["LER-SDSC", "LSR-PB", "LER-BLR"],
        "priority": "critical",
        "telemetry_rate_mbps": 8.4,
        "uplink_freq_ghz": 2.065,
        "downlink_freq_ghz": 2.245,
        "launched": "2024-12-30",
        "color": "#3b82f6"
    },
    {
        "id": "INSAT-3DS",
        "name": "INSAT-3DS Meteorological",
        "type": "GSLV",
        "status": "active",
        "phase": "GEO Orbit Operations",
        "orbit": "GEO 36000km",
        "primary_lsp": "LSP-104",
        "tracking_stations": ["LER-MU", "LSR-HASAN", "LER-BLR"],
        "priority": "high",
        "telemetry_rate_mbps": 2.1,
        "uplink_freq_ghz": 6.0,
        "downlink_freq_ghz": 4.0,
        "launched": "2024-02-17",
        "color": "#10b981"
    },
    {
        "id": "ADITYA-L1",
        "name": "Aditya-L1 Solar Observatory",
        "type": "PSLV-XL",
        "status": "active",
        "phase": "L1 Halo Orbit Science",
        "orbit": "L1 Halo ~1.5M km",
        "primary_lsp": "LSP-104",
        "tracking_stations": ["LER-MU", "LER-BIAK", "LER-BLR"],
        "priority": "high",
        "telemetry_rate_mbps": 0.4,
        "uplink_freq_ghz": 2.3,
        "downlink_freq_ghz": 2.245,
        "launched": "2023-09-02",
        "color": "#f59e0b"
    },
    {
        "id": "LVM3-M4",
        "name": "LVM3-M4 / OneWeb Launch",
        "type": "LVM3",
        "status": "standby",
        "phase": "T-04:30 Pre-launch Hold",
        "orbit": "LEO 1200km",
        "primary_lsp": "LSP-101",
        "tracking_stations": ["LER-SDSC", "LSR-PB"],
        "priority": "critical",
        "telemetry_rate_mbps": 0.0,
        "uplink_freq_ghz": 2.065,
        "downlink_freq_ghz": 2.245,
        "launched": None,
        "color": "#8b5cf6"
    }
]

# ─── OAM Event Templates ───────────────────────────────────────────────────────

OAM_EVENT_TEMPLATES = [
    {"type": "CCM_OK",       "severity": "info",     "msg": "CCM continuity check OK on {lsp}"},
    {"type": "CCM_LOSS",     "severity": "critical",  "msg": "CCM loss detected on {lsp} — peer unreachable"},
    {"type": "LB_PASS",      "severity": "info",     "msg": "Loopback test passed on {lsp} — RTT {rtt}ms"},
    {"type": "LB_FAIL",      "severity": "warning",  "msg": "Loopback timeout on {lsp} — path verification failed"},
    {"type": "AIS_RECEIVED", "severity": "critical",  "msg": "AIS signal received on {lsp} — upstream failure propagating"},
    {"type": "LDI_SENT",     "severity": "warning",  "msg": "Link Down Indication sent on {lsp} — notifying downstream"},
    {"type": "PERF_THRESH",  "severity": "warning",  "msg": "Performance threshold exceeded on {lsp} — frame loss {loss}%"},
    {"type": "RDI_RECVD",    "severity": "warning",  "msg": "Remote Defect Indication on {lsp} — far-end alarm active"},
    {"type": "LT_COMPLETE",  "severity": "info",     "msg": "Link Trace complete on {lsp} — {hops} hops discovered"},
    {"type": "FRR_TRIGGER",  "severity": "critical",  "msg": "Fast Reroute triggered on {lsp} — switching to backup path in <50ms"},
    {"type": "FRR_RESTORED", "severity": "info",     "msg": "Fast Reroute restored on {lsp} — primary path back online"},
    {"type": "BFD_DOWN",     "severity": "critical",  "msg": "BFD session DOWN on {lsp} — link failure confirmed"},
    {"type": "BFD_UP",       "severity": "info",     "msg": "BFD session UP on {lsp} — link restored"},
]

LSP_IDS = ["LSP-101", "LSP-102", "LSP-103", "LSP-104", "LSP-105", "LSP-106"]


class OAMMonitor:
    """Simulates real-time OAM events for ISRO MPLS network"""

    MAX_EVENTS = 50

    def __init__(self):
        self.events: List[dict] = []
        self._tick = 0
        self._generate_initial()

    def _generate_initial(self):
        for _ in range(12):
            self.events.append(self._make_event(
                ts_offset=random.randint(30, 600)
            ))
        self.events.sort(key=lambda e: e["timestamp"], reverse=True)

    def _make_event(self, ts_offset=0, lsp_id=None, template=None) -> dict:
        lsp     = lsp_id or random.choice(LSP_IDS)
        tmpl    = template or random.choice(OAM_EVENT_TEMPLATES)
        rtt     = random.randint(8, 95)
        loss    = round(random.uniform(0.1, 8.0), 2)
        hops    = random.randint(2, 5)
        msg     = tmpl["msg"].format(lsp=lsp, rtt=rtt, loss=loss, hops=hops)
        ts      = datetime.utcnow() - timedelta(seconds=ts_offset)
        return {
            "id":       f"OAM-{self._tick:04d}-{random.randint(100,999)}",
            "type":     tmpl["type"],
            "severity": tmpl["severity"],
            "lsp":      lsp,
            "message":  msg,
            "timestamp": ts.isoformat(),
            "age_s":    ts_offset,
        }

    def tick(self, active_anomalies: list):
        self._tick += 1
        # Higher chance of events during anomalies
        threshold = 0.25 if active_anomalies else 0.08
        if random.random() < threshold:
            # Pick relevant template
            if active_anomalies:
                critical_templates = [t for t in OAM_EVENT_TEMPLATES if t["severity"] == "critical"]
                tmpl = random.choice(critical_templates)
            else:
                tmpl = random.choice(OAM_EVENT_TEMPLATES)
            ev = self._make_event(ts_offset=0, template=tmpl)
            self.events.insert(0, ev)
            if len(self.events) > self.MAX_EVENTS:
                self.events.pop()

    def get_recent(self, n: int = 20) -> List[dict]:
        return self.events[:n]

    def get_stats(self) -> dict:
        total = len(self.events)
        crit  = sum(1 for e in self.events if e["severity"] == "critical")
        warn  = sum(1 for e in self.events if e["severity"] == "warning")
        info  = total - crit - warn
        return {
            "total": total,
            "critical": crit,
            "warning": warn,
            "info": info,
            "frr_triggers": sum(1 for e in self.events if e["type"] == "FRR_TRIGGER"),
        }


class MissionMonitor:
    """Tracks active ISRO missions and their telemetry impact"""

    def __init__(self):
        self.missions = [dict(m) for m in MISSIONS]

    def tick(self):
        for m in self.missions:
            if m["status"] == "active":
                # Telemetry rate varies slightly
                base = next((om["telemetry_rate_mbps"] for om in MISSIONS if om["id"] == m["id"]), 1.0)
                m["telemetry_rate_mbps"] = max(0, base + random.gauss(0, base * 0.05))
                # Signal quality
                m["signal_quality_pct"] = round(random.uniform(82, 99.5), 1)
                m["link_margin_db"]     = round(random.uniform(4.5, 18.0), 1)
            elif m["status"] == "standby":
                m["signal_quality_pct"] = 0
                m["link_margin_db"]     = 0

    def get_all(self) -> List[dict]:
        return self.missions

    def get_active(self) -> List[dict]:
        return [m for m in self.missions if m["status"] == "active"]


# Singletons
oam_monitor     = OAMMonitor()
mission_monitor = MissionMonitor()
