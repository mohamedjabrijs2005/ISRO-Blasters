"""
Predictive ML Engine for MPLS Network Failure Forecasting
Uses exponential smoothing + linear regression + anomaly scoring
Runs 100% offline — no cloud dependencies
"""

import math
import random
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta


class ExponentialSmoothing:
    """Holt-Winters Double Exponential Smoothing for time-series forecasting"""

    def __init__(self, alpha: float = 0.3, beta: float = 0.1):
        self.alpha = alpha
        self.beta = beta
        self.level = None
        self.trend = None

    def fit(self, series: List[float]) -> None:
        if len(series) < 2:
            self.level = series[0] if series else 0.0
            self.trend = 0.0
            return
        self.level = series[0]
        self.trend = series[1] - series[0]
        for val in series[1:]:
            prev_level = self.level
            self.level = self.alpha * val + (1 - self.alpha) * (self.level + self.trend)
            self.trend = self.beta * (self.level - prev_level) + (1 - self.beta) * self.trend

    def forecast(self, steps: int) -> List[float]:
        return [self.level + i * self.trend for i in range(1, steps + 1)]


class AnomalyScorer:
    """Z-score based anomaly detection with sliding window"""

    def __init__(self, window: int = 20):
        self.window = window

    def score(self, series: List[float], current: float) -> float:
        if len(series) < 3:
            return 0.0
        recent = series[-self.window:]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std = math.sqrt(variance) if variance > 0 else 0.0001
        return abs(current - mean) / std


class LSPPredictor:
    """Per-LSP predictive model with multi-metric forecasting"""

    FORECAST_STEPS = 8       # ~15 minutes ahead at 2s/tick
    WARNING_UTIL   = 0.75
    CRITICAL_UTIL  = 0.85
    WARNING_LATENCY = 50     # ms
    CRITICAL_LATENCY = 80    # ms
    WARNING_LOSS   = 0.02
    CRITICAL_LOSS  = 0.05

    def __init__(self, lsp_id: str):
        self.lsp_id = lsp_id
        self.util_model   = ExponentialSmoothing(alpha=0.35, beta=0.12)
        self.lat_model    = ExponentialSmoothing(alpha=0.25, beta=0.08)
        self.loss_model   = ExponentialSmoothing(alpha=0.40, beta=0.05)
        self.util_scorer  = AnomalyScorer(window=20)
        self.lat_scorer   = AnomalyScorer(window=20)
        self.risk_history: List[float] = []

    def analyze(self, history: List[dict]) -> dict:
        """Analyze telemetry history and return predictions + risk assessment"""
        if len(history) < 5:
            return self._empty_result()

        utils  = [h["utilization"]  for h in history]
        lats   = [h["latency_ms"]   for h in history]
        losses = [h["packet_loss"]  for h in history]

        # Fit models
        self.util_model.fit(utils)
        self.lat_model.fit(lats)
        self.loss_model.fit(losses)

        # Forecasts
        util_forecast = [max(0, min(1, v)) for v in self.util_model.forecast(self.FORECAST_STEPS)]
        lat_forecast  = [max(0, v)         for v in self.lat_model.forecast(self.FORECAST_STEPS)]
        loss_forecast = [max(0, min(1, v)) for v in self.loss_model.forecast(self.FORECAST_STEPS)]

        # Anomaly scores
        util_z  = self.util_scorer.score(utils,  utils[-1])
        lat_z   = self.lat_scorer.score(lats,    lats[-1])

        # Peak predicted values
        peak_util  = max(util_forecast)
        peak_lat   = max(lat_forecast)
        peak_loss  = max(loss_forecast)

        # Time-to-threshold estimation (in "ticks" * 2s = minutes*30)
        time_to_warning  = self._time_to_threshold(util_forecast, self.WARNING_UTIL)
        time_to_critical = self._time_to_threshold(util_forecast, self.CRITICAL_UTIL)

        # Composite risk score (0-100)
        risk = self._compute_risk(
            peak_util, peak_lat, peak_loss,
            util_z, lat_z,
            time_to_critical
        )
        self.risk_history.append(risk)
        if len(self.risk_history) > 60:
            self.risk_history.pop(0)

        # Risk level
        if risk >= 70:
            risk_level = "critical"
            alert = self._generate_alert(risk, peak_util, peak_lat, peak_loss, time_to_critical)
        elif risk >= 45:
            risk_level = "warning"
            alert = self._generate_alert(risk, peak_util, peak_lat, peak_loss, time_to_warning)
        else:
            risk_level = "nominal"
            alert = None

        return {
            "lsp_id": self.lsp_id,
            "risk_score": round(risk, 1),
            "risk_level": risk_level,
            "alert": alert,
            "forecast": {
                "utilization": [round(v, 4) for v in util_forecast],
                "latency_ms":  [round(v, 2) for v in lat_forecast],
                "packet_loss": [round(v, 5) for v in loss_forecast],
            },
            "peak": {
                "utilization":  round(peak_util,  4),
                "latency_ms":   round(peak_lat,   2),
                "packet_loss":  round(peak_loss,  5),
            },
            "anomaly_score": {
                "utilization": round(util_z, 2),
                "latency_ms":  round(lat_z, 2),
            },
            "time_to_warning_min":  self._ticks_to_minutes(time_to_warning),
            "time_to_critical_min": self._ticks_to_minutes(time_to_critical),
            "current": {
                "utilization": round(utils[-1],  4),
                "latency_ms":  round(lats[-1],   2),
                "packet_loss": round(losses[-1], 5),
            }
        }

    def _time_to_threshold(self, forecast: List[float], threshold: float) -> Optional[int]:
        for i, v in enumerate(forecast):
            if v >= threshold:
                return i + 1
        return None

    def _ticks_to_minutes(self, ticks: Optional[int]) -> Optional[float]:
        if ticks is None:
            return None
        return round(ticks * 2 / 60, 1)

    def _compute_risk(self, util, lat, loss, util_z, lat_z, time_crit) -> float:
        score = 0.0
        # Utilization component (0–40 pts)
        score += min(40, (util / 0.9) * 40)
        # Latency component (0–25 pts)
        score += min(25, (lat / 100) * 25)
        # Packet loss component (0–20 pts)
        score += min(20, (loss / 0.1) * 20)
        # Anomaly component (0–10 pts)
        score += min(10, (util_z / 3) * 10)
        # Urgency bonus (0–5 pts) — closer to threshold = higher risk
        if time_crit is not None:
            score += max(0, 5 - time_crit * 0.5)
        return min(100, max(0, score))

    def _generate_alert(self, risk, peak_util, peak_lat, peak_loss, time_threshold) -> dict:
        reasons = []
        actions = []

        if peak_util > self.CRITICAL_UTIL:
            reasons.append(f"link utilization forecasted to reach {peak_util:.0%}")
            actions.append("Pre-provision alternate LSP via backup path")
        elif peak_util > self.WARNING_UTIL:
            reasons.append(f"utilization trending toward {peak_util:.0%}")
            actions.append("Monitor closely and prepare reroute plan")

        if peak_lat > self.CRITICAL_LATENCY:
            reasons.append(f"latency spike predicted at {peak_lat:.0f}ms")
            actions.append("Check OAM continuity checks on this LSP segment")

        if peak_loss > self.CRITICAL_LOSS:
            reasons.append(f"packet loss forecasted at {peak_loss:.2%}")
            actions.append("Inspect physical layer and optical power levels")

        time_str = f"in ~{self._ticks_to_minutes(time_threshold)} min" if time_threshold else "soon"

        return {
            "lsp_id": self.lsp_id,
            "risk_score": round(risk, 1),
            "message": f"⚠ {self.lsp_id}: {'; '.join(reasons)} {time_str}.",
            "reasons": reasons,
            "suggested_actions": actions,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _empty_result(self) -> dict:
        return {
            "lsp_id": self.lsp_id,
            "risk_score": 0.0,
            "risk_level": "nominal",
            "alert": None,
            "forecast": {"utilization": [], "latency_ms": [], "packet_loss": []},
            "peak": {"utilization": 0, "latency_ms": 0, "packet_loss": 0},
            "anomaly_score": {"utilization": 0, "latency_ms": 0},
            "time_to_warning_min": None,
            "time_to_critical_min": None,
            "current": {"utilization": 0, "latency_ms": 0, "packet_loss": 0}
        }


class NetworkPredictor:
    """Aggregates per-LSP predictions into network-wide health intelligence"""

    def __init__(self, lsp_ids: List[str]):
        self.models: Dict[str, LSPPredictor] = {
            lsp_id: LSPPredictor(lsp_id) for lsp_id in lsp_ids
        }

    def analyze_all(self, history: Dict[str, List[dict]]) -> dict:
        results = {}
        alerts = []
        network_risk = 0.0

        for lsp_id, model in self.models.items():
            lsp_history = history.get(lsp_id, [])
            result = model.analyze(lsp_history)
            results[lsp_id] = result

            if result["alert"]:
                alerts.append(result["alert"])

            network_risk = max(network_risk, result["risk_score"])

        # Sort alerts by risk score
        alerts.sort(key=lambda a: a["risk_score"], reverse=True)

        if network_risk >= 70:
            network_health = "critical"
        elif network_risk >= 45:
            network_health = "degraded"
        else:
            network_health = "healthy"

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "network_health": network_health,
            "network_risk_score": round(network_risk, 1),
            "lsp_predictions": results,
            "active_alerts": alerts[:5],   # Top 5 alerts
            "total_alerts": len(alerts),
        }


# Singleton
from backend.simulator import LSP_DEFINITIONS
predictor = NetworkPredictor([lsp["id"] for lsp in LSP_DEFINITIONS])
