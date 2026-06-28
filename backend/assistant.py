"""
Local LLM + RAG Assistant for Air-Gapped MPLS Copilot
Interfaces with Ollama local HTTP API — zero internet dependency
Includes built-in knowledge base for offline fallback
"""

import json
import re
import time
from datetime import datetime
from typing import Optional, List
import urllib.request
import urllib.error


# ─── ISRO MPLS Knowledge Base (used when LLM unavailable) ────────────────────

KNOWLEDGE_BASE = {
    "lsp": """
Label Switched Paths (LSPs) are predetermined routes through the MPLS network. In ISRO's network:
- LSP-101: Sriharikota Launch Control → Bengaluru MCF (Critical, Telemetry)
- LSP-102: Bengaluru MCF → Hassan Satellite Control (High, Command Channel)
- LSP-103: Port Blair Tracking → Bengaluru MCF (Critical, Real-time Tracking)
- LSP-104: Mauritius Deep Space → Bengaluru MCF (High, Deep Space Data)
- LSP-105: Biak Equatorial → Bengaluru MCF (Medium, Equatorial Tracking)
- LSP-106: Sriharikota → Hassan MCF (High, Command Backup)
- LSP-107 & LSP-108: Backup paths for Traffic Engineering rerouting

LSP health indicators:
- Utilization >85%: Critical — immediate reroute required
- Utilization 70–85%: Warning — prepare alternate path
- Packet Loss >5%: Critical — physical layer issue likely
- Latency >80ms: Critical — affects real-time telemetry integrity
""",
    "oam": """
OAM (Operations, Administration, Maintenance) in ISRO MPLS network:
- Continuity Check Messages (CCM): Sent every 100ms on critical LSPs
- Link Trace (LT): Used to diagnose path faults across LSR hops
- Loopback (LB): Verifies end-to-end LSP connectivity
- Performance Monitoring: Delay, delay variation, frame loss ratio
- Alarm Indication Signal (AIS): Propagated when upstream failure detected

OAM fault response procedures:
1. Detect fault via CCM loss / AIS reception
2. Identify affected LSP and traffic type
3. Trigger Traffic Engineering (TE) reroute via RSVP-TE signaling
4. Verify alternate path availability and capacity
5. Commit switchover — pre-planned paths activate within 50ms (FRR)
""",
    "traffic_engineering": """
Traffic Engineering (TE) in MPLS allows dynamic rerouting:
- Fast Reroute (FRR): Pre-computed backup LSPs activated in <50ms on failure
- Constraint-Based Routing: Routes traffic based on bandwidth, latency, priority
- CSPF (Constrained Shortest Path First): Algorithm to find TE paths
- Preemption: Higher priority LSPs can preempt lower priority ones

For ISRO missions:
- Launch telemetry (Priority 1): Always protected, FRR enabled
- Satellite command channels (Priority 2): Hot standby paths pre-provisioned
- Housekeeping data (Priority 3): Best-effort, may be rerouted during congestion
""",
    "congestion": """
Congestion management in ISRO MPLS network:
- WRED (Weighted Random Early Detection): Applied at LERs to manage queue depth
- QoS policies: EF (Expedited Forwarding) for telemetry, AF for commands, BE for rest
- Burst absorption: Link buffers handle short burst traffic during launch events
- Traffic shaping: Rate limiters on non-critical LSPs during mission-critical windows

Common congestion causes:
1. Launch events — sudden surge in telemetry from PSLV/GSLV/LVM3
2. Solar weather events — reduced link efficiency, higher retransmission rates
3. Ground station maintenance windows — traffic concentrated on fewer paths
4. Satellite anomalies — increased housekeeping data downloads
""",
    "nodes": """
ISRO Ground Network Node roles:
- LER-BLR (Bengaluru): Master Control Facility (MCF) — main hub, 40 Gbps capacity
- LER-SDSC (Sriharikota): SHAR Launch Center — launch telemetry origin
- LSR-PB (Port Blair): Tracking station — equatorial orbit coverage
- LER-MU (Mauritius): Deep space tracking — outer planet/interplanetary missions
- LER-BIAK (Biak, Indonesia): Equatorial tracking for GEO satellite orbit raising
- LSR-HASAN (Hassan): Secondary MCF — satellite TTC operations

LER = Label Edge Router (ingress/egress of MPLS domain)
LSR = Label Switch Router (internal MPLS forwarding node)
""",
    "failure": """
Common failure modes and remediation in ISRO MPLS network:

1. Fiber Cut: 
   Symptom: LSP status DOWN, CCM loss, AIS propagation
   Action: Activate FRR backup LSP immediately, dispatch physical team
   
2. Router Hardware Fault:
   Symptom: Node goes unreachable, all LSPs through node fail
   Action: Traffic redistributed to alternate nodes via TE, spare router activation
   
3. Software/Protocol Bug:
   Symptom: Label table corruption, forwarding plane errors
   Action: Graceful Restart, route table refresh, escalate to NOC Level 2
   
4. Congestion (Traffic Overload):
   Symptom: High utilization, packet drops, latency increase
   Action: Reroute lower-priority LSPs, apply WRED, throttle non-critical traffic
   
5. RF/Optical Degradation:
   Symptom: Increasing BER, intermittent packet loss, latency jitter
   Action: Check optical power budgets, check RF link margins, adjust modulation
"""
}

SYSTEM_PROMPT = """You are Astraeus, an expert AI Network Operations Copilot for ISRO's (Indian Space Research Organisation) air-gapped MPLS mission-critical network. You assist Network Operations Center (NOC) engineers.

Your expertise covers:
- MPLS networking (LSPs, LDP, RSVP-TE, Traffic Engineering, Fast Reroute)
- ISRO ground station network topology (Bengaluru, Sriharikota, Port Blair, Mauritius, Biak, Hassan)
- OAM fault detection and recovery procedures
- Network telemetry analysis and anomaly diagnosis
- Predictive maintenance and proactive network operations

Response style:
- Be precise and technical but clear
- Always recommend actionable steps for the operator
- Reference specific LSP IDs, node names, and metrics when available
- Prioritize mission-critical paths (telemetry during launches)
- Keep responses concise but complete
- Format using plain text with clear sections (no markdown in chat)

You operate completely offline — no internet access. All knowledge is local."""


class OllamaClient:
    """Lightweight Ollama HTTP client — no external libraries needed"""

    DEFAULT_HOST = "http://localhost:11434"
    TIMEOUT_S    = 30

    def __init__(self, host: str = DEFAULT_HOST, model: str = "phi3:mini"):
        self.host  = host.rstrip("/")
        self.model = model
        self._available = None

    def check_availability(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                self._available = len(models) > 0
                # Pick best available model
                for preferred in ["phi3:mini", "phi3", "mistral", "llama3", "llama2", "gemma"]:
                    for m in models:
                        if preferred in m.lower():
                            self.model = m
                            break
                return self._available
        except Exception:
            self._available = False
            return False

    def chat(self, messages: List[dict], temperature: float = 0.3) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 512}
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.TIMEOUT_S) as resp:
            result = json.loads(resp.read())
            return result["message"]["content"]


class RAGRetriever:
    """Simple keyword-based retrieval over ISRO MPLS knowledge base"""

    TOPIC_KEYWORDS = {
        "lsp":               ["lsp", "label", "switched", "path", "lsp-10", "degraded", "utilization"],
        "oam":               ["oam", "continuity", "loopback", "fault", "ccm", "ais", "link trace"],
        "traffic_engineering": ["reroute", "rerouting", "traffic engineering", "te", "frr", "fast reroute", "alternate", "backup path"],
        "congestion":        ["congestion", "saturation", "overload", "bandwidth", "queue", "packet drop", "loss"],
        "nodes":             ["node", "router", "ler", "lsr", "bengaluru", "sriharikota", "port blair", "mauritius", "biak", "hassan"],
        "failure":           ["fail", "failure", "down", "outage", "fiber cut", "hardware", "bug", "degradation"],
    }

    def retrieve(self, query: str, top_k: int = 3) -> str:
        query_lower = query.lower()
        scores: dict = {}
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score > 0:
                scores[topic] = score

        if not scores:
            # Return general context
            return KNOWLEDGE_BASE["nodes"] + "\n" + KNOWLEDGE_BASE["lsp"]

        top_topics = sorted(scores, key=scores.get, reverse=True)[:top_k]
        return "\n\n---\n\n".join(KNOWLEDGE_BASE[t] for t in top_topics)


class NetworkContextBuilder:
    """Builds structured network context from live telemetry for LLM prompts"""

    @staticmethod
    def build(snapshot: dict, predictions: dict) -> str:
        lines = ["=== LIVE NETWORK STATUS ==="]

        # Active anomalies
        anomalies = snapshot.get("active_anomalies", [])
        if anomalies:
            lines.append("\nACTIVE ANOMALIES:")
            for a in anomalies:
                lines.append(f"  • {a['name']}: {a['description']}")

        # Critical/warning LSPs
        lines.append("\nLSP STATUS (critical/warning only):")
        for lsp in snapshot.get("lsps", []):
            health = lsp.get("health", "nominal")
            if health in ("critical", "warning"):
                lines.append(
                    f"  {lsp['id']} [{lsp['src']} → {lsp['dst']}] "
                    f"util={lsp['utilization']:.0%} lat={lsp['latency_ms']:.1f}ms "
                    f"loss={lsp['packet_loss']:.2%} health={health.upper()}"
                )

        # Predictions
        lines.append("\nML PREDICTIONS (top risks):")
        pred_data = predictions.get("lsp_predictions", {})
        alerts = predictions.get("active_alerts", [])
        if alerts:
            for alert in alerts[:3]:
                lines.append(f"  ⚠ {alert['message']}")
                for action in alert.get("suggested_actions", [])[:2]:
                    lines.append(f"    → {action}")
        else:
            lines.append("  No active alerts — network operating normally.")

        lines.append(f"\nNETWORK HEALTH: {predictions.get('network_health', 'unknown').upper()}")
        lines.append(f"OVERALL RISK SCORE: {predictions.get('network_risk_score', 0)}/100")

        return "\n".join(lines)


class AstraeusCopilot:
    """Main AI Assistant — combines RAG retrieval + LLM generation"""

    MAX_HISTORY = 10

    def __init__(self):
        self.llm     = OllamaClient()
        self.rag     = RAGRetriever()
        self.context = NetworkContextBuilder()
        self.history: List[dict] = []
        self.llm_available: Optional[bool] = None
        self._check_llm()

    def _check_llm(self):
        self.llm_available = self.llm.check_availability()

    def _rule_based_response(self, query: str, snapshot: dict, predictions: dict) -> str:
        """Fallback responses when Ollama is not available"""
        query_lower = query.lower()

        # Find highest risk LSP
        pred_data   = predictions.get("lsp_predictions", {})
        alerts      = predictions.get("active_alerts", [])
        lsps        = snapshot.get("lsps", [])
        anomalies   = snapshot.get("active_anomalies", [])

        if re.search(r"(risk|danger|critical|warning)", query_lower):
            if alerts:
                resp = "Current risk assessment:\n"
                for a in alerts[:3]:
                    resp += f"\n• {a['message']}\n"
                    for act in a.get("suggested_actions", []):
                        resp += f"  → Recommended: {act}\n"
                return resp
            return "All LSPs are currently within normal operating parameters. No immediate risks detected."

        if re.search(r"(lsp|path|route|switch)", query_lower):
            # Find mentioned LSP
            for lsp in lsps:
                if lsp["id"].lower() in query_lower:
                    pred = pred_data.get(lsp["id"], {})
                    return (
                        f"{lsp['id']} ({lsp['src']} → {lsp['dst']}):\n"
                        f"  Status: {lsp.get('status', 'UP')} | Health: {lsp.get('health','nominal').upper()}\n"
                        f"  Utilization: {lsp['utilization']:.1%}\n"
                        f"  Latency: {lsp['latency_ms']:.1f} ms\n"
                        f"  Packet Loss: {lsp['packet_loss']:.3%}\n"
                        f"  Risk Score: {pred.get('risk_score', 0):.0f}/100\n"
                        f"  Forecast Peak Util: {pred.get('peak', {}).get('utilization', 0):.1%}"
                    )
            # General LSP summary
            lines = ["LSP Status Summary:"]
            for lsp in sorted(lsps, key=lambda x: x.get("utilization", 0), reverse=True)[:5]:
                lines.append(f"  {lsp['id']}: {lsp['utilization']:.0%} util, {lsp['health'].upper()}")
            return "\n".join(lines)

        if re.search(r"(reroute|rerouting|alternate|backup)", query_lower):
            context = self.rag.retrieve("reroute traffic engineering frr")
            return f"Rerouting Guidance:\n\n{context[:600]}"

        if re.search(r"(anomal|event|incident|outage)", query_lower):
            if anomalies:
                resp = "Active Network Events:\n"
                for a in anomalies:
                    resp += f"\n• {a['name']}: {a['description']}"
                return resp
            return "No active anomalies detected. Network is stable."

        if re.search(r"(node|router|station|location)", query_lower):
            return self.rag.retrieve("node router ler lsr location")[:800]

        if re.search(r"(oam|maintenance|continuity|check)", query_lower):
            return self.rag.retrieve("oam continuity maintenance")[:800]

        # Default: network health summary
        health = predictions.get("network_health", "unknown")
        risk   = predictions.get("network_risk_score", 0)
        lsp_statuses = ", ".join(
            f"{l['id']}:{l['health'].upper()}"
            for l in sorted(lsps, key=lambda x: x.get("utilization", 0), reverse=True)[:4]
        )
        return (
            f"Network Health: {health.upper()} (Risk Score: {risk:.0f}/100)\n\n"
            f"Top LSPs by utilization: {lsp_statuses}\n\n"
            f"Active Alerts: {len(alerts)}\n\n"
            f"Type 'show lsp LSP-101', 'show risks', 'explain rerouting', or 'show anomalies' for details."
        )

    def query(self, user_query: str, snapshot: dict, predictions: dict) -> dict:
        """Process a natural language query and return AI response"""
        start = time.time()

        # Build context
        net_context = self.context.build(snapshot, predictions)
        rag_context = self.rag.retrieve(user_query)

        if self.llm_available:
            try:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT + f"\n\n{net_context}\n\nRELEVANT KNOWLEDGE:\n{rag_context}"},
                    *self.history[-self.MAX_HISTORY:],
                    {"role": "user", "content": user_query},
                ]
                response = self.llm.chat(messages)
                mode = "llm"
            except Exception as e:
                response = self._rule_based_response(user_query, snapshot, predictions)
                mode = "fallback"
                self.llm_available = False
        else:
            response = self._rule_based_response(user_query, snapshot, predictions)
            mode = "fallback"

        # Update conversation history
        self.history.append({"role": "user", "content": user_query})
        self.history.append({"role": "assistant", "content": response})
        if len(self.history) > self.MAX_HISTORY * 2:
            self.history = self.history[-(self.MAX_HISTORY * 2):]

        return {
            "response":      response,
            "mode":          mode,
            "model":         self.llm.model if self.llm_available else "rule-based",
            "latency_ms":    round((time.time() - start) * 1000),
            "timestamp":     datetime.utcnow().isoformat(),
            "llm_available": self.llm_available,
        }


# Singleton
copilot = AstraeusCopilot()
