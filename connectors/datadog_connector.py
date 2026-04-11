import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from data.service_topology import Alert, MetricSnapshot

log = logging.getLogger(__name__)


class DatadogConnector:
    """Fetches metrics and monitors from Datadog."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_key: Optional[str] = None,
        site: str = "datadoghq.com",
    ) -> None:
        self._api_key = api_key or os.environ.get("DATADOG_API_KEY", "")
        self._app_key = app_key or os.environ.get("DATADOG_APP_KEY", "")
        self._base_url = f"https://api.{site}/api"
        self._headers = {
            "DD-API-KEY": self._api_key,
            "DD-APPLICATION-KEY": self._app_key,
            "Content-Type": "application/json",
        }

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make an authenticated request to Datadog API."""
        url = f"{self._base_url}{endpoint}"
        resp = requests.get(url, headers=self._headers, params=params or {}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def query_metric(
        self,
        service: str,
        metric_type: str,
        time_range_minutes: int = 30,
    ) -> Optional[MetricSnapshot]:
        """Query a specific metric from Datadog."""
        now = int(datetime.now(timezone.utc).timestamp())
        start = now - (time_range_minutes * 60)

        # Map our metric types to Datadog metric names
        metric_map = {
            "cpu": f"system.cpu.user{{service:{service}}}",
            "memory": f"system.mem.used{{service:{service}}}",
            "latency": f"trace.http.request.duration{{service:{service}}}",
            "error_rate": f"trace.http.request.errors{{service:{service}}}",
            "connections": f"postgresql.connections{{service:{service}}}",
        }

        dd_query = metric_map.get(metric_type)
        if not dd_query:
            return None

        try:
            data = self._request("/v1/query", {
                "from": str(start),
                "to": str(now),
                "query": dd_query,
            })

            series = data.get("series", [])
            if not series:
                return None

            points = series[0].get("pointlist", [])
            if not points:
                return None

            current_val = points[-1][1] if points[-1][1] is not None else 0.0

            # Calculate normal from average of first few points
            early_points = [p[1] for p in points[:5] if p[1] is not None]
            normal_val = sum(early_points) / len(early_points) if early_points else current_val

            trend = "stable"
            if current_val > normal_val * 2:
                trend = "spike"
            elif current_val > normal_val * 1.3:
                trend = "rising"
            elif current_val < normal_val * 0.7:
                trend = "falling"

            units = {"cpu": "%", "memory": "MB", "latency": "ms", "error_rate": "%", "connections": "count"}

            return MetricSnapshot(
                service=service,
                metric_type=metric_type,
                current_value=round(current_val, 1),
                normal_value=round(normal_val, 1),
                unit=units.get(metric_type, ""),
                timestamp=datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
                trend=trend,
            )

        except Exception as e:
            log.error("Error querying metric: %s", e)
            return None

    def query_all_metrics(
        self,
        service: str,
        time_range_minutes: int = 30,
    ) -> Dict[str, MetricSnapshot]:
        """Query all standard metrics for a service."""
        results: Dict[str, MetricSnapshot] = {}
        for metric_type in ("cpu", "memory", "latency", "error_rate"):
            snapshot = self.query_metric(service, metric_type, time_range_minutes)
            if snapshot:
                results[metric_type] = snapshot
        return results

    def fetch_alerts(
        self,
        time_range_minutes: int = 30,
        severity: Optional[str] = None,
        service: Optional[str] = None,
    ) -> List[Alert]:
        """Fetch triggered monitors from Datadog as Alert objects."""
        try:
            data = self._request("/v1/monitor", {
                "monitor_tags": f"service:{service}" if service else "",
            })
        except Exception as e:
            log.error("Error fetching monitors: %s", e)
            return []

        severity_map = {
            "Alert": "CRITICAL",
            "Warn": "WARNING",
            "No Data": "INFO",
            "OK": "INFO",
        }

        alerts: List[Alert] = []
        for monitor in data if isinstance(data, list) else []:
            state = monitor.get("overall_state", "OK")
            if state == "OK":
                continue

            dd_severity = severity_map.get(state, "INFO")
            if severity and dd_severity != severity:
                continue

            tags = monitor.get("tags", [])
            svc = service or next((t.split(":")[1] for t in tags if t.startswith("service:")), "unknown")

            alerts.append(Alert(
                alert_id=str(monitor.get("id", "")),
                severity=dd_severity,
                service=svc,
                title=monitor.get("name", "Untitled monitor"),
                description=monitor.get("message", "")[:200],
                timestamp=monitor.get("modified", ""),
                status="firing" if state == "Alert" else "warning",
            ))

        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mute a Datadog monitor (acknowledgement equivalent)."""
        try:
            url = f"{self._base_url}/v1/monitor/{alert_id}/mute"
            resp = requests.post(url, headers=self._headers, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            log.error("Error muting monitor %s: %s", alert_id, e)
            return False
