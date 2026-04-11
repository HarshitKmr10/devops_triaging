import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from data.service_topology import LogEntry

log = logging.getLogger(__name__)


class ELKConnector:
    """Fetches logs from Elasticsearch or Grafana Loki."""

    def __init__(
        self,
        elasticsearch_url: Optional[str] = None,
        loki_url: Optional[str] = None,
        api_key: Optional[str] = None,
        index_pattern: str = "logs-*",
    ) -> None:
        self._es_url = elasticsearch_url or os.environ.get("ELASTICSEARCH_URL", "")
        self._loki_url = loki_url or os.environ.get("LOKI_URL", "")
        self._api_key = api_key or os.environ.get("ELASTICSEARCH_API_KEY", "")
        self._index_pattern = index_pattern
        self._use_loki = bool(self._loki_url and not self._es_url)

    def search_logs(
        self,
        service: str,
        keyword: Optional[str] = None,
        level: Optional[str] = None,
        time_range_minutes: int = 30,
        limit: int = 50,
    ) -> List[LogEntry]:
        """Search logs for a service."""
        if self._use_loki:
            return self._search_loki(service, keyword, level, time_range_minutes, limit)
        return self._search_elasticsearch(service, keyword, level, time_range_minutes, limit)

    def _search_elasticsearch(
        self,
        service: str,
        keyword: Optional[str],
        level: Optional[str],
        time_range_minutes: int,
        limit: int,
    ) -> List[LogEntry]:
        """Search logs via Elasticsearch."""
        if not self._es_url:
            return []

        now = datetime.now(timezone.utc)
        since = now - timedelta(minutes=time_range_minutes)

        # Build Elasticsearch query
        must_clauses = [
            {"term": {"service.name": service}},
            {"range": {"@timestamp": {"gte": since.isoformat(), "lte": now.isoformat()}}},
        ]
        if keyword:
            must_clauses.append({"match": {"message": keyword}})
        if level:
            must_clauses.append({"term": {"log.level": level.upper()}})

        query = {
            "query": {"bool": {"must": must_clauses}},
            "sort": [{"@timestamp": "asc"}],
            "size": limit,
        }

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"ApiKey {self._api_key}"

        try:
            url = f"{self._es_url}/{self._index_pattern}/_search"
            resp = requests.post(url, json=query, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("Elasticsearch error: %s", e)
            return []

        entries: List[LogEntry] = []
        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            entries.append(LogEntry(
                timestamp=src.get("@timestamp", ""),
                level=src.get("log", {}).get("level", "INFO").upper(),
                service=src.get("service", {}).get("name", service),
                message=src.get("message", ""),
                trace_id=src.get("trace", {}).get("id"),
            ))

        return entries

    def _search_loki(
        self,
        service: str,
        keyword: Optional[str],
        level: Optional[str],
        time_range_minutes: int,
        limit: int,
    ) -> List[LogEntry]:
        """Search logs via Grafana Loki."""
        if not self._loki_url:
            return []

        now = datetime.now(timezone.utc)
        since = now - timedelta(minutes=time_range_minutes)

        # Build LogQL query
        label_selectors = [f'service="{service}"']
        if level:
            label_selectors.append(f'level="{level.lower()}"')

        logql = "{" + ",".join(label_selectors) + "}"
        if keyword:
            logql += f' |= "{keyword}"'

        try:
            url = f"{self._loki_url}/loki/api/v1/query_range"
            params = {
                "query": logql,
                "start": str(int(since.timestamp() * 1e9)),
                "end": str(int(now.timestamp() * 1e9)),
                "limit": str(limit),
                "direction": "forward",
            }
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("Loki error: %s", e)
            return []

        entries: List[LogEntry] = []
        for stream in data.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            svc = labels.get("service", service)
            lvl = labels.get("level", "INFO").upper()

            for ts_ns, line in stream.get("values", []):
                ts = datetime.fromtimestamp(int(ts_ns) / 1e9, tz=timezone.utc).isoformat()
                entries.append(LogEntry(
                    timestamp=ts,
                    level=lvl,
                    service=svc,
                    message=line,
                ))

        return entries
