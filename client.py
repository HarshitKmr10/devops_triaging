"""DevOps Incident Response Environment Client."""

from typing import Any, Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

try:
    from .models import IncidentAction, IncidentObservation, IncidentState
except ImportError:
    from models import IncidentAction, IncidentObservation, IncidentState


class IncidentResponseClient(
    EnvClient[IncidentAction, IncidentObservation, IncidentState]
):
    """
    Client for the DevOps Incident Response Environment.

    Maintains a persistent WebSocket connection to the environment server
    for efficient multi-step incident response interactions.
    """

    def _step_payload(self, action: IncidentAction) -> Dict[str, Any]:
        """Convert IncidentAction to JSON payload for step message."""
        return action.model_dump(exclude_none=True)

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[IncidentObservation]:
        """Parse server response into StepResult[IncidentObservation]."""
        obs_data = payload.get("observation", {})

        observation = IncidentObservation(
            output=obs_data.get("output", payload.get("output", "")),
            system_status=obs_data.get("system_status", ""),
            active_alerts_count=obs_data.get("active_alerts_count", 0),
            feedback=obs_data.get("feedback", ""),
            task_description=obs_data.get("task_description", ""),
            available_actions=obs_data.get("available_actions", []),
            services=obs_data.get("services", []),
            step_number=obs_data.get("step_number", 0),
            max_steps=obs_data.get("max_steps", 30),
            task_id=obs_data.get("task_id", ""),
            difficulty=obs_data.get("difficulty", ""),
            reward=payload.get("reward"),
            done=payload.get("done", False),
            metadata=payload.get("info", payload.get("metadata", {})),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> IncidentState:
        """Parse server response into IncidentState."""
        return IncidentState(
            task_id=payload.get("task_id", ""),
            task_name=payload.get("task_name", ""),
            difficulty=payload.get("difficulty", ""),
            step=payload.get("step", 0),
            max_steps=payload.get("max_steps", 30),
            total_reward=payload.get("total_reward", 0.0),
            actions_taken=payload.get("actions_taken", []),
            services_investigated=payload.get("services_investigated", []),
            incident_resolved=payload.get("incident_resolved", False),
            done=payload.get("done", False),
        )
