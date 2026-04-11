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

    action_type: str = Field(...)
    service_name: Optional[str] = Field(default=None)
    keyword: Optional[str] = Field(default=None)
    time_range: Optional[str] = Field(default=None)
    metric_type: Optional[str] = Field(default=None)
    severity: Optional[str] = Field(default=None)
    root_cause: Optional[str] = Field(default=None)
    remediation: Optional[str] = Field(default=None)
    team: Optional[str] = Field(default=None)
    command: Optional[str] = Field(default=None)


class IncidentObservation(Observation):
    """Observation returned after each agent action."""

    output: str = Field(default="")
    system_status: str = Field(default="")
    active_alerts_count: int = Field(default=0)
    feedback: str = Field(default="")
    task_description: str = Field(default="")
    available_actions: List[str] = Field(default_factory=lambda: list(VALID_ACTION_TYPES))
    services: List[str] = Field(default_factory=list)
    step_number: int = Field(default=0)
    max_steps: int = Field(default=30)
    task_id: str = Field(default="")
    difficulty: str = Field(default="")


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
