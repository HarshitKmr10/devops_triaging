"""
Data models for the DevOps Incident Response Environment.

Defines the action and observation types for SRE incident response scenarios.
Agents investigate production incidents by querying alerts, logs, metrics,
inspecting services, and executing remediation actions.
"""

from typing import Any, Dict, List, Optional

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


VALID_ACTION_TYPES = [
    "view_alerts",
    "query_logs",
    "query_metrics",
    "inspect_service",
    "check_dependencies",
    "run_diagnostic",
    "classify_severity",
    "identify_root_cause",
    "execute_remediation",
    "escalate",
]


class IncidentAction(Action):
    """Action the SRE agent can take during incident response."""

    action_type: str = Field(
        ...,
        description=(
            "Type of action to perform. One of: view_alerts, query_logs, "
            "query_metrics, inspect_service, check_dependencies, run_diagnostic, "
            "classify_severity, identify_root_cause, execute_remediation, escalate"
        ),
    )
    service_name: Optional[str] = Field(
        default=None,
        description="Target service name (required for most actions)",
    )
    keyword: Optional[str] = Field(
        default=None,
        description="Search keyword for log queries",
    )
    time_range: Optional[str] = Field(
        default=None,
        description="Time range for queries (e.g., 'last_15m', 'last_1h')",
    )
    metric_type: Optional[str] = Field(
        default=None,
        description="Metric to query: cpu, memory, latency, error_rate, connections",
    )
    severity: Optional[str] = Field(
        default=None,
        description="Incident severity for classify_severity: P1, P2, P3, P4",
    )
    root_cause: Optional[str] = Field(
        default=None,
        description="Root cause description for identify_root_cause",
    )
    remediation: Optional[str] = Field(
        default=None,
        description="Remediation action for execute_remediation",
    )
    team: Optional[str] = Field(
        default=None,
        description="Team name for escalation",
    )
    command: Optional[str] = Field(
        default=None,
        description="Diagnostic command to run",
    )


class IncidentObservation(Observation):
    """Observation returned after each agent action."""

    output: str = Field(
        default="",
        description="Primary output from the action (logs, metrics, service info, etc.)",
    )
    system_status: str = Field(
        default="",
        description="Current overall system health summary",
    )
    active_alerts_count: int = Field(
        default=0,
        description="Number of currently active alerts",
    )
    feedback: str = Field(
        default="",
        description="Feedback on the agent's action quality",
    )
    task_description: str = Field(
        default="",
        description="Description of what the agent needs to accomplish",
    )
    available_actions: List[str] = Field(
        default_factory=lambda: list(VALID_ACTION_TYPES),
        description="List of valid action types",
    )
    services: List[str] = Field(
        default_factory=list,
        description="List of services in the environment",
    )
    step_number: int = Field(
        default=0,
        description="Current step number in the episode",
    )
    max_steps: int = Field(
        default=30,
        description="Maximum steps allowed",
    )
    task_id: str = Field(
        default="",
        description="Current task identifier",
    )
    difficulty: str = Field(
        default="",
        description="Task difficulty: easy, medium, hard",
    )


class IncidentState(State):
    """Current state of the incident response episode."""

    task_id: str = ""
    task_name: str = ""
    difficulty: str = ""
    step: int = 0
    max_steps: int = 30
    total_reward: float = 0.0
    actions_taken: List[str] = Field(default_factory=list)
    services_investigated: List[str] = Field(default_factory=list)
    incident_resolved: bool = False
    done: bool = False
