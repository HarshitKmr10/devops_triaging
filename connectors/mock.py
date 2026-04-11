from typing import Dict, List, Optional

from data.service_topology import (
    ALERT_TRIAGE_ALERTS,
    ALERT_TRIAGE_LOGS,
    ALERT_TRIAGE_METRICS,
    Alert,
    LogEntry,
    MetricSnapshot,
    SERVICES,
)


class MockConnector:

    def __init__(
        self,
        alerts: Optional[tuple[Alert, ...]] = None,
        logs: Optional[Dict[str, tuple[LogEntry, ...]]] = None,
        metrics: Optional[Dict[str, Dict[str, MetricSnapshot]]] = None,
    ) -> None:
        self._alerts = alerts or ALERT_TRIAGE_ALERTS
        self._logs = logs or ALERT_TRIAGE_LOGS
        self._metrics = metrics or ALERT_TRIAGE_METRICS

    # AlertSource
    def fetch_alerts(
        self,
        time_range_minutes: int = 30,
        severity: Optional[str] = None,
        service: Optional[str] = None,
    ) -> List[Alert]:
        result = list(self._alerts)
        if severity:
            result = [a for a in result if a.severity == severity]
        if service:
            result = [a for a in result if a.service == service]
        return result

    def acknowledge_alert(self, alert_id: str) -> bool:
        return True

    # LogSource
    def search_logs(
        self,
        service: str,
        keyword: Optional[str] = None,
        level: Optional[str] = None,
        time_range_minutes: int = 30,
        limit: int = 50,
    ) -> List[LogEntry]:
        logs = list(self._logs.get(service, ()))
        if keyword:
            logs = [e for e in logs if keyword.lower() in e.message.lower()]
        if level:
            logs = [e for e in logs if e.level == level.upper()]
        return logs[:limit]

    # MetricSource
    def query_metric(
        self,
        service: str,
        metric_type: str,
        time_range_minutes: int = 30,
    ) -> Optional[MetricSnapshot]:
        svc_metrics = self._metrics.get(service, {})
        return svc_metrics.get(metric_type)

    def query_all_metrics(
        self,
        service: str,
        time_range_minutes: int = 30,
    ) -> Dict[str, MetricSnapshot]:
        return dict(self._metrics.get(service, {}))

    # ServiceRegistry
    def get_service(self, name: str) -> Optional[Dict]:
        svc = SERVICES.get(name)
        if not svc:
            return None
        return {
            "name": svc.name,
            "team": svc.team,
            "description": svc.description,
            "dependencies": list(svc.dependencies),
        }

    def get_dependencies(self, name: str) -> List[str]:
        svc = SERVICES.get(name)
        return list(svc.dependencies) if svc else []

    def get_dependents(self, name: str) -> List[str]:
        return [
            s.name for s in SERVICES.values()
            if name in s.dependencies
        ]

    def list_services(self) -> List[str]:
        return list(SERVICES.keys())
