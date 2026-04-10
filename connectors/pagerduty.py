"""
PagerDuty connector for live alert ingestion.

Fetches real incidents and alerts from PagerDuty API and converts
them to our Alert data model for use in live incident scenarios.

Requires: PAGERDUTY_API_KEY environment variable
Docs: https://developer.pagerduty.com/api-reference/
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from data.service_topology import Alert


_SEVERITY_MAP = {
    "critical": "CRITICAL",
    "high": "CRITICAL",
    "warning": "WARNING",
    "error": "WARNING",
    "info": "INFO",
    "low": "INFO",
}


class PagerDutyConnector:
    """Fetches alerts from PagerDuty and converts to our Alert model."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.pagerduty.com",
    ) -> None:
        self._api_key = api_key or os.environ.get("PAGERDUTY_API_KEY", "")
        self._base_url = base_url
        self._headers = {
            "Authorization": f"Token token={self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make an authenticated request to PagerDuty API."""
        url = f"{self._base_url}{endpoint}"
        resp = requests.get(url, headers=self._headers, params=params or {}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def fetch_alerts(
        self,
        time_range_minutes: int = 30,
        severity: Optional[str] = None,
        service: Optional[str] = None,
    ) -> List[Alert]:
        """Fetch active incidents from PagerDuty as Alert objects."""
        since = (datetime.now(timezone.utc) - timedelta(minutes=time_range_minutes)).isoformat()
        params: Dict[str, str] = {
            "since": since,
            "statuses[]": "triggered,acknowledged",
            "sort_by": "created_at:desc",
            "limit": "50",
        }
        if service:
            params["service_ids[]"] = service

        try:
            data = self._request("/incidents", params)
        except Exception as e:
            print(f"[PagerDuty] Error fetching incidents: {e}")
            return []

        alerts: List[Alert] = []
        for incident in data.get("incidents", []):
            pd_severity = incident.get("urgency", "info").lower()
            our_severity = _SEVERITY_MAP.get(pd_severity, "INFO")

            if severity and our_severity != severity:
                continue

            svc_name = "unknown"
            if incident.get("service"):
                svc_name = incident["service"].get("summary", "unknown")

            alerts.append(Alert(
                alert_id=incident.get("incident_number", "PD-???"),
                severity=our_severity,
                service=svc_name,
                title=incident.get("title", "Untitled incident"),
                description=incident.get("description", "") or incident.get("title", ""),
                timestamp=incident.get("created_at", ""),
                status="firing" if incident.get("status") == "triggered" else "acknowledged",
            ))

        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge a PagerDuty incident."""
        try:
            url = f"{self._base_url}/incidents/{alert_id}"
            payload = {
                "incident": {
                    "type": "incident_reference",
                    "status": "acknowledged",
                }
            }
            resp = requests.put(
                url, headers=self._headers, json=payload, timeout=10
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"[PagerDuty] Error acknowledging {alert_id}: {e}")
            return False

    def fetch_incident_timeline(self, incident_id: str) -> List[Dict]:
        """Fetch the log entries / timeline for an incident."""
        try:
            data = self._request(f"/incidents/{incident_id}/log_entries", {
                "limit": "100",
                "sort_by": "created_at:asc",
            })
            return data.get("log_entries", [])
        except Exception as e:
            print(f"[PagerDuty] Error fetching timeline: {e}")
            return []
