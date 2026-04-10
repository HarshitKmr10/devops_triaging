"""
Protocol definitions for data source connectors.

Any connector implementing these protocols can be plugged into
the environment as a drop-in replacement for mock data.
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable

from data.service_topology import Alert, LogEntry, MetricSnapshot


@runtime_checkable
class AlertSource(Protocol):
    """Protocol for fetching alerts from a monitoring system."""

    def fetch_alerts(
        self,
        time_range_minutes: int = 30,
        severity: Optional[str] = None,
        service: Optional[str] = None,
    ) -> List[Alert]:
        """Fetch active alerts within the time range."""
        ...

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        ...


@runtime_checkable
class LogSource(Protocol):
    """Protocol for searching logs from a logging system."""

    def search_logs(
        self,
        service: str,
        keyword: Optional[str] = None,
        level: Optional[str] = None,
        time_range_minutes: int = 30,
        limit: int = 50,
    ) -> List[LogEntry]:
        """Search logs for a service."""
        ...


@runtime_checkable
class MetricSource(Protocol):
    """Protocol for querying metrics from a monitoring system."""

    def query_metric(
        self,
        service: str,
        metric_type: str,
        time_range_minutes: int = 30,
    ) -> Optional[MetricSnapshot]:
        """Query a specific metric for a service."""
        ...

    def query_all_metrics(
        self,
        service: str,
        time_range_minutes: int = 30,
    ) -> Dict[str, MetricSnapshot]:
        """Query all available metrics for a service."""
        ...


@runtime_checkable
class ServiceRegistry(Protocol):
    """Protocol for service discovery and topology."""

    def get_service(self, name: str) -> Optional[Dict]:
        """Get service details."""
        ...

    def get_dependencies(self, name: str) -> List[str]:
        """Get direct dependencies of a service."""
        ...

    def get_dependents(self, name: str) -> List[str]:
        """Get services that depend on this one."""
        ...

    def list_services(self) -> List[str]:
        """List all known services."""
        ...
