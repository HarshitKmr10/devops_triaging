from typing import Dict, List, Optional, Protocol, runtime_checkable

from data.service_topology import Alert, LogEntry, MetricSnapshot


@runtime_checkable
class AlertSource(Protocol):

    def fetch_alerts(
        self,
        time_range_minutes: int = 30,
        severity: Optional[str] = None,
        service: Optional[str] = None,
    ) -> List[Alert]: ...

    def acknowledge_alert(self, alert_id: str) -> bool: ...


@runtime_checkable
class LogSource(Protocol):

    def search_logs(
        self,
        service: str,
        keyword: Optional[str] = None,
        level: Optional[str] = None,
        time_range_minutes: int = 30,
        limit: int = 50,
    ) -> List[LogEntry]: ...


@runtime_checkable
class MetricSource(Protocol):

    def query_metric(
        self,
        service: str,
        metric_type: str,
        time_range_minutes: int = 30,
    ) -> Optional[MetricSnapshot]: ...

    def query_all_metrics(
        self,
        service: str,
        time_range_minutes: int = 30,
    ) -> Dict[str, MetricSnapshot]: ...


@runtime_checkable
class ServiceRegistry(Protocol):

    def get_service(self, name: str) -> Optional[Dict]: ...

    def get_dependencies(self, name: str) -> List[str]: ...

    def get_dependents(self, name: str) -> List[str]: ...

    def list_services(self) -> List[str]: ...
