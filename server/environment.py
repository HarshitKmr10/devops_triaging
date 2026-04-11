from typing import Any, List, Optional

from openenv.core.env_server import Environment

try:
    from ..models import IncidentAction, IncidentObservation, IncidentState
    from ..scenarios import SCENARIOS
except ImportError:
    from models import IncidentAction, IncidentObservation, IncidentState
    from scenarios import SCENARIOS


TASK_NAMES = list(SCENARIOS.keys())
DEFAULT_TASK = "alert_triage"


class IncidentResponseEnvironment(
    Environment[IncidentAction, IncidentObservation, IncidentState]
):
    """OpenEnv environment for DevOps incident response evaluation."""

    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self) -> None:
        self._task_id: Optional[str] = None
        self._scenario: Any = None
        self._step_idx: int = 0
        self._done: bool = False
        self._rewards: List[float] = []

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        self._task_id = kwargs.get("task_id") or kwargs.get("task") or DEFAULT_TASK

        if self._task_id not in SCENARIOS:
            self._task_id = DEFAULT_TASK

        scenario_cls = SCENARIOS[self._task_id]
        self._scenario = scenario_cls()
        self._step_idx = 0
        self._done = False
        self._rewards = []

        config = self._scenario.config

        return IncidentObservation(
            output=(
                f"INCIDENT RESPONSE INITIATED\n"
                f"{'=' * 50}\n"
                f"Task: {config.task_name} ({config.difficulty})\n"
                f"System Status: {config.system_status}\n"
                f"{'=' * 50}\n\n"
                f"{config.description}\n\n"
                f"Available services: {', '.join(config.services)}\n"
                f"Max steps: {config.max_steps}\n\n"
                f"Begin your investigation. Use 'view_alerts' to start."
            ),
            system_status=config.system_status,
            active_alerts_count=0,
            feedback="Incident assigned to you. Begin investigation.",
            task_description=config.description,
            services=list(config.services),
            step_number=0,
            max_steps=config.max_steps,
            task_id=self._task_id,
            difficulty=config.difficulty,
            done=False,
            reward=0.0,
        )

    def step(self, action: IncidentAction) -> IncidentObservation:
        if self._scenario is None:
            raise RuntimeError("Call reset() before step()")
        if self._done:
            raise RuntimeError("Episode is finished. Call reset() to start a new one.")

        result = self._scenario.handle_action(
            action_type=action.action_type,
            service_name=action.service_name,
            keyword=action.keyword,
            metric_type=action.metric_type,
            severity=action.severity,
            root_cause=action.root_cause,
            remediation=action.remediation,
            team=action.team,
            command=action.command,
        )

        self._rewards.append(result.reward)
        self._step_idx += 1
        self._done = result.done or self._scenario.is_done

        config = self._scenario.config

        # Build system status with progress info
        total_reward = self._scenario.total_reward
        status = config.system_status
        if self._done and total_reward >= 0.6:
            status = "RECOVERING - Remediation applied. Services stabilizing."
        elif self._done:
            status = "UNRESOLVED - Episode ended without full resolution."

        # Include score breakdown in output when episode ends
        output = result.output
        if self._done:
            breakdown = self._scenario.get_score_breakdown()
            output = (output or "") + "\n\n" + breakdown.format()
            if self._scenario.safety_violations:
                output += "\n\nSafety Violations:\n"
                for v in self._scenario.safety_violations:
                    output += f"  - {v}\n"

        return IncidentObservation(
            output=output,
            system_status=status,
            active_alerts_count=len(config.services),
            feedback=result.feedback,
            task_description=config.description,
            services=list(config.services),
            step_number=self._step_idx,
            max_steps=config.max_steps,
            task_id=self._task_id or "",
            difficulty=config.difficulty,
            done=self._done,
            reward=result.reward,
            metadata={
                "step": self._step_idx,
                "task_id": self._task_id,
                "total_reward": total_reward,
                "rewards_so_far": list(self._rewards),
                "score_breakdown": {
                    "investigation": breakdown.investigation,
                    "diagnosis": breakdown.diagnosis,
                    "resolution": breakdown.resolution,
                    "safety": breakdown.safety,
                    "efficiency": breakdown.efficiency,
                    "weighted_total": breakdown.total,
                } if self._done else None,
                "safety_violations": self._scenario.safety_violations if self._done else [],
            },
        )

    @property
    def state(self) -> IncidentState:
        """Return current episode state."""
        if self._scenario is None:
            return IncidentState()

        config = self._scenario.config
        return IncidentState(
            task_id=self._task_id or "",
            task_name=config.task_name,
            difficulty=config.difficulty,
            step=self._step_idx,
            max_steps=config.max_steps,
            total_reward=self._scenario.total_reward,
            actions_taken=self._scenario.actions_taken,
            services_investigated=self._scenario.services_investigated,
            incident_resolved=self._done and self._scenario.total_reward >= 0.6,
            done=self._done,
        )
