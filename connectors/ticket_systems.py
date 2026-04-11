import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TicketData:
    """Unified ticket representation across all systems."""

    ticket_id: str
    title: str
    description: str
    status: str  # open, in_progress, resolved, closed
    priority: str  # P1, P2, P3, P4
    assignee: Optional[str] = None
    team: Optional[str] = None
    category: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    labels: tuple[str, ...] = ()
    source_system: str = ""
    raw_data: Optional[Dict[str, Any]] = None


class TicketSystemConnector(ABC):
    """Abstract base for ticket system integrations."""

    @abstractmethod
    def create_incident(
        self,
        title: str,
        description: str,
        priority: str,
        team: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> TicketData: ...

    @abstractmethod
    def update_ticket(
        self,
        ticket_id: str,
        comment: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> bool: ...

    @abstractmethod
    def fetch_open_tickets(
        self,
        team: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[TicketData]: ...

    @abstractmethod
    def add_agent_findings(
        self,
        ticket_id: str,
        root_cause: str,
        remediation: str,
        score_breakdown: Dict[str, float],
        trajectory_summary: str,
    ) -> bool: ...


class ServiceNowConnector(TicketSystemConnector):
    """ServiceNow ITSM integration via REST API."""

    def __init__(
        self,
        instance: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._instance = instance or os.environ.get("SERVICENOW_INSTANCE", "")
        self._auth = (
            username or os.environ.get("SERVICENOW_USER", ""),
            password or os.environ.get("SERVICENOW_PASSWORD", ""),
        )
        self._base_url = f"https://{self._instance}.service-now.com/api/now"
        self._headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        url = f"{self._base_url}{endpoint}"
        resp = requests.request(
            method, url, auth=self._auth, headers=self._headers,
            json=data, timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("result", {})

    def create_incident(
        self,
        title: str,
        description: str,
        priority: str,
        team: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> TicketData:
        priority_map = {"P1": "1", "P2": "2", "P3": "3", "P4": "4"}
        data = {
            "short_description": title,
            "description": description,
            "priority": priority_map.get(priority, "3"),
            "category": "Software",
            "assignment_group": team or "",
        }

        try:
            result = self._request("POST", "/table/incident", data)
            return TicketData(
                ticket_id=result.get("number", ""),
                title=title,
                description=description,
                status="open",
                priority=priority,
                team=team,
                source_system="servicenow",
                raw_data=result,
            )
        except Exception as e:
            log.error("ServiceNow create incident error: %s", e)
            return TicketData(
                ticket_id="ERROR", title=title, description=str(e),
                status="error", priority=priority, source_system="servicenow",
            )

    def update_ticket(
        self,
        ticket_id: str,
        comment: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> bool:
        data: Dict[str, str] = {}
        if comment:
            data["work_notes"] = comment
        if status:
            status_map = {"in_progress": "2", "resolved": "6", "closed": "7"}
            data["state"] = status_map.get(status, "2")
        if priority:
            priority_map = {"P1": "1", "P2": "2", "P3": "3", "P4": "4"}
            data["priority"] = priority_map.get(priority, "3")

        try:
            # Get sys_id from number
            query_result = self._request("GET", f"/table/incident?sysparm_query=number={ticket_id}&sysparm_limit=1")
            if isinstance(query_result, list) and query_result:
                sys_id = query_result[0].get("sys_id", "")
                self._request("PATCH", f"/table/incident/{sys_id}", data)
                return True
        except Exception as e:
            log.error("ServiceNow update error: %s", e)
        return False

    def fetch_open_tickets(
        self,
        team: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[TicketData]:
        query_parts = ["state!=7"]  # Not closed
        if team:
            query_parts.append(f"assignment_group.name={team}")
        if priority:
            priority_map = {"P1": "1", "P2": "2", "P3": "3", "P4": "4"}
            query_parts.append(f"priority={priority_map.get(priority, '3')}")

        query = "^".join(query_parts)

        try:
            results = self._request("GET", f"/table/incident?sysparm_query={query}&sysparm_limit={limit}")
            if not isinstance(results, list):
                results = [results] if results else []

            tickets = []
            for r in results:
                sn_priority = r.get("priority", "3")
                p_map = {"1": "P1", "2": "P2", "3": "P3", "4": "P4"}
                tickets.append(TicketData(
                    ticket_id=r.get("number", ""),
                    title=r.get("short_description", ""),
                    description=r.get("description", ""),
                    status="open",
                    priority=p_map.get(sn_priority, "P3"),
                    team=r.get("assignment_group", {}).get("display_value", ""),
                    source_system="servicenow",
                ))
            return tickets
        except Exception as e:
            log.error("ServiceNow fetch error: %s", e)
            return []

    def add_agent_findings(
        self,
        ticket_id: str,
        root_cause: str,
        remediation: str,
        score_breakdown: Dict[str, float],
        trajectory_summary: str,
    ) -> bool:
        comment = (
            f"=== AI Agent Investigation Report ===\n\n"
            f"Root Cause: {root_cause}\n\n"
            f"Recommended Remediation: {remediation}\n\n"
            f"Score Breakdown:\n"
            + "\n".join(f"  {k}: {v:.2f}" for k, v in score_breakdown.items())
            + f"\n\nInvestigation Summary:\n{trajectory_summary}"
        )
        return self.update_ticket(ticket_id, comment=comment)


class JiraConnector(TicketSystemConnector):
    """Jira Cloud integration via REST API v3."""

    def __init__(
        self,
        url: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        project_key: str = "INC",
    ) -> None:
        self._url = (url or os.environ.get("JIRA_URL", "")).rstrip("/")
        self._email = email or os.environ.get("JIRA_EMAIL", "")
        self._token = api_token or os.environ.get("JIRA_API_TOKEN", "")
        self._project = project_key
        self._auth = (self._email, self._token)
        self._headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        url = f"{self._url}/rest/api/3{endpoint}"
        resp = requests.request(
            method, url, auth=self._auth, headers=self._headers,
            json=data, timeout=15,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def create_incident(
        self,
        title: str,
        description: str,
        priority: str,
        team: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> TicketData:
        priority_map = {"P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low"}
        data = {
            "fields": {
                "project": {"key": self._project},
                "summary": title,
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
                },
                "issuetype": {"name": "Bug"},
                "priority": {"name": priority_map.get(priority, "Medium")},
                "labels": labels or ["incident", "ai-agent"],
            }
        }

        try:
            result = self._request("POST", "/issue", data)
            return TicketData(
                ticket_id=result.get("key", ""),
                title=title,
                description=description,
                status="open",
                priority=priority,
                team=team,
                labels=tuple(labels or []),
                source_system="jira",
                raw_data=result,
            )
        except Exception as e:
            log.error("Jira create error: %s", e)
            return TicketData(
                ticket_id="ERROR", title=title, description=str(e),
                status="error", priority=priority, source_system="jira",
            )

    def update_ticket(
        self,
        ticket_id: str,
        comment: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> bool:
        try:
            if comment:
                self._request("POST", f"/issue/{ticket_id}/comment", {
                    "body": {
                        "type": "doc", "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}],
                    }
                })
            if priority:
                priority_map = {"P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low"}
                self._request("PUT", f"/issue/{ticket_id}", {
                    "fields": {"priority": {"name": priority_map.get(priority, "Medium")}}
                })
            return True
        except Exception as e:
            log.error("Jira update error: %s", e)
            return False

    def fetch_open_tickets(
        self,
        team: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[TicketData]:
        jql_parts = [f"project={self._project}", "status != Done"]
        if priority:
            priority_map = {"P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low"}
            jql_parts.append(f"priority = {priority_map.get(priority, 'Medium')}")

        jql = " AND ".join(jql_parts)

        try:
            result = self._request("GET", f"/search?jql={jql}&maxResults={limit}")
            tickets = []
            for issue in result.get("issues", []):
                fields = issue.get("fields", {})
                p_name = fields.get("priority", {}).get("name", "Medium")
                p_map = {"Highest": "P1", "High": "P2", "Medium": "P3", "Low": "P4"}
                tickets.append(TicketData(
                    ticket_id=issue.get("key", ""),
                    title=fields.get("summary", ""),
                    description="",
                    status=fields.get("status", {}).get("name", "open").lower(),
                    priority=p_map.get(p_name, "P3"),
                    labels=tuple(fields.get("labels", [])),
                    source_system="jira",
                ))
            return tickets
        except Exception as e:
            log.error("Jira fetch error: %s", e)
            return []

    def add_agent_findings(
        self,
        ticket_id: str,
        root_cause: str,
        remediation: str,
        score_breakdown: Dict[str, float],
        trajectory_summary: str,
    ) -> bool:
        comment = (
            f"h2. AI Agent Investigation Report\n\n"
            f"*Root Cause:* {root_cause}\n\n"
            f"*Recommended Remediation:* {remediation}\n\n"
            f"*Score Breakdown:*\n"
            + "\n".join(f"* {k}: {v:.2f}" for k, v in score_breakdown.items())
            + f"\n\n*Investigation Summary:*\n{trajectory_summary}"
        )
        return self.update_ticket(ticket_id, comment=comment)


class LinearConnector(TicketSystemConnector):
    """Linear integration via GraphQL API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("LINEAR_API_KEY", "")
        self._team_id = team_id or os.environ.get("LINEAR_TEAM_ID", "")
        self._url = "https://api.linear.app/graphql"
        self._headers = {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
        }

    def _graphql(self, query: str, variables: Optional[Dict] = None) -> Dict:
        resp = requests.post(
            self._url, headers=self._headers,
            json={"query": query, "variables": variables or {}},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        return data.get("data", {})

    def create_incident(
        self,
        title: str,
        description: str,
        priority: str,
        team: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> TicketData:
        priority_map = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
        mutation = """
        mutation CreateIssue($title: String!, $description: String!, $teamId: String!, $priority: Int) {
            issueCreate(input: {title: $title, description: $description, teamId: $teamId, priority: $priority}) {
                issue { id identifier title }
            }
        }
        """
        try:
            result = self._graphql(mutation, {
                "title": title,
                "description": description,
                "teamId": self._team_id,
                "priority": priority_map.get(priority, 3),
            })
            issue = result.get("issueCreate", {}).get("issue", {})
            return TicketData(
                ticket_id=issue.get("identifier", ""),
                title=title,
                description=description,
                status="open",
                priority=priority,
                source_system="linear",
            )
        except Exception as e:
            log.error("Linear create error: %s", e)
            return TicketData(
                ticket_id="ERROR", title=title, description=str(e),
                status="error", priority=priority, source_system="linear",
            )

    def update_ticket(
        self,
        ticket_id: str,
        comment: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> bool:
        try:
            if comment:
                # First get issue ID from identifier
                query = """
                query GetIssue($filter: IssueFilter) {
                    issues(filter: $filter, first: 1) {
                        nodes { id }
                    }
                }
                """
                result = self._graphql(query, {
                    "filter": {"identifier": {"eq": ticket_id}}
                })
                nodes = result.get("issues", {}).get("nodes", [])
                if nodes:
                    issue_id = nodes[0]["id"]
                    mutation = """
                    mutation AddComment($issueId: String!, $body: String!) {
                        commentCreate(input: {issueId: $issueId, body: $body}) {
                            comment { id }
                        }
                    }
                    """
                    self._graphql(mutation, {"issueId": issue_id, "body": comment})
            return True
        except Exception as e:
            log.error("Linear update error: %s", e)
            return False

    def fetch_open_tickets(
        self,
        team: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[TicketData]:
        query = """
        query OpenIssues($teamId: String, $first: Int) {
            issues(filter: {team: {id: {eq: $teamId}}, state: {type: {nin: ["completed", "canceled"]}}}, first: $first) {
                nodes { identifier title description priority state { name } }
            }
        }
        """
        try:
            result = self._graphql(query, {
                "teamId": team or self._team_id,
                "first": limit,
            })
            p_map = {1: "P1", 2: "P2", 3: "P3", 4: "P4", 0: "P4"}
            tickets = []
            for node in result.get("issues", {}).get("nodes", []):
                tickets.append(TicketData(
                    ticket_id=node.get("identifier", ""),
                    title=node.get("title", ""),
                    description=node.get("description", ""),
                    status=node.get("state", {}).get("name", "open").lower(),
                    priority=p_map.get(node.get("priority", 3), "P3"),
                    source_system="linear",
                ))
            return tickets
        except Exception as e:
            log.error("Linear fetch error: %s", e)
            return []

    def add_agent_findings(
        self,
        ticket_id: str,
        root_cause: str,
        remediation: str,
        score_breakdown: Dict[str, float],
        trajectory_summary: str,
    ) -> bool:
        comment = (
            f"## AI Agent Investigation Report\n\n"
            f"**Root Cause:** {root_cause}\n\n"
            f"**Recommended Remediation:** {remediation}\n\n"
            f"**Score Breakdown:**\n"
            + "\n".join(f"- {k}: {v:.2f}" for k, v in score_breakdown.items())
            + f"\n\n**Investigation Summary:**\n{trajectory_summary}"
        )
        return self.update_ticket(ticket_id, comment=comment)
