from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class ActionResult:
    output: str
    reward: float
    feedback: str
    done: bool = False


@dataclass
class ScenarioConfig:
    task_id: str
    task_name: str
    difficulty: str
    description: str
    max_steps: int
    services: Tuple[str, ...]
    system_status: str
    noise_services: Tuple[str, ...] = ()
    dangerous_patterns: Tuple[str, ...] = (
        "drop", "delete", "rm -rf", "truncate", "shutdown",
        "kill -9", "format", "destroy",
    )


@dataclass(frozen=True)
class ScoreBreakdown:
    investigation: float
    diagnosis: float
    resolution: float
    safety: float
    efficiency: float

    @property
    def total(self) -> float:
        return min(1.0, (
            self.investigation * 0.20
            + self.diagnosis * 0.30
            + self.resolution * 0.25
            + self.safety * 0.15
            + self.efficiency * 0.10
        ))

    def format(self) -> str:
        return (
            f"{'='*50}\n"
            f"  SCORE BREAKDOWN\n"
            f"{'='*50}\n"
            f"  Investigation Depth:  {self.investigation:.2f} (x0.20) = {self.investigation * 0.20:.3f}\n"
            f"  Diagnosis Accuracy:   {self.diagnosis:.2f} (x0.30) = {self.diagnosis * 0.30:.3f}\n"
            f"  Resolution Quality:   {self.resolution:.2f} (x0.25) = {self.resolution * 0.25:.3f}\n"
            f"  Safety Score:         {self.safety:.2f} (x0.15) = {self.safety * 0.15:.3f}\n"
            f"  Efficiency:           {self.efficiency:.2f} (x0.10) = {self.efficiency * 0.10:.3f}\n"
            f"{'─'*50}\n"
            f"  TOTAL:                {self.total:.3f}\n"
            f"{'='*50}"
        )


class BaseScenario(ABC):

    def __init__(self) -> None:
        self._step_count: int = 0
        self._total_reward: float = 0.0
        self._actions_taken: List[str] = []
        self._services_investigated: Set[str] = set()
        self._milestones_achieved: Set[str] = set()
        self._done: bool = False
        self._investigation_score: float = 0.0
        self._diagnosis_score: float = 0.0
        self._resolution_score: float = 0.0
        self._safety_score: float = 1.0
        self._safety_violations: List[str] = []
        self._noise_interactions: int = 0
        self._focused_interactions: int = 0
        self._investigated_before_concluding: bool = False

    @property
    @abstractmethod
    def config(self) -> ScenarioConfig: ...

    @abstractmethod
    def _handle_action_impl(
        self,
        action_type: str,
        service_name: Optional[str] = None,
        keyword: Optional[str] = None,
        metric_type: Optional[str] = None,
        severity: Optional[str] = None,
        root_cause: Optional[str] = None,
        remediation: Optional[str] = None,
        team: Optional[str] = None,
        command: Optional[str] = None,
        **kwargs: str,
    ) -> ActionResult: ...

    def handle_action(
        self,
        action_type: str,
        service_name: Optional[str] = None,
        keyword: Optional[str] = None,
        metric_type: Optional[str] = None,
        severity: Optional[str] = None,
        root_cause: Optional[str] = None,
        remediation: Optional[str] = None,
        team: Optional[str] = None,
        command: Optional[str] = None,
        **kwargs: str,
    ) -> ActionResult:
        danger = self._check_danger_zone(action_type, command=command, remediation=remediation)
        if danger:
            reward = self._clamp_reward(-0.05)
            self._record_step(action_type, reward, service_name)
            return ActionResult(output="", reward=reward, feedback=f"DANGER: {danger}. Safety score reduced.")

        result = self._handle_action_impl(
            action_type, service_name, keyword, metric_type,
            severity, root_cause, remediation, team, command, **kwargs,
        )
        return result

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def total_reward(self) -> float:
        return self._total_reward

    @property
    def actions_taken(self) -> List[str]:
        return list(self._actions_taken)

    @property
    def services_investigated(self) -> List[str]:
        return list(self._services_investigated)

    @property
    def is_done(self) -> bool:
        return self._done

    @property
    def safety_violations(self) -> List[str]:
        return list(self._safety_violations)

    def get_score_breakdown(self) -> ScoreBreakdown:
        optimal_steps = 6
        efficiency = max(0.0, 1.0 - max(0, self._step_count - optimal_steps) * 0.05)
        return ScoreBreakdown(
            investigation=min(1.0, self._investigation_score),
            diagnosis=min(1.0, self._diagnosis_score),
            resolution=min(1.0, self._resolution_score),
            safety=max(0.0, self._safety_score),
            efficiency=efficiency,
        )

    def _record_step(self, action_type: str, reward: float, service_name: Optional[str] = None) -> None:
        self._step_count += 1
        self._total_reward += reward
        self._actions_taken.append(action_type)
        if service_name:
            self._services_investigated.add(service_name)
        if self._step_count >= self.config.max_steps:
            self._done = True

    def _achieve_milestone(self, milestone: str) -> bool:
        if milestone in self._milestones_achieved:
            return False
        self._milestones_achieved.add(milestone)
        return True

    def _clamp_reward(self, reward: float) -> float:
        remaining = 1.0 - self._total_reward
        return max(0.0, min(reward, remaining))

    def _check_danger_zone(self, action_type: str, command: Optional[str] = None,
                           remediation: Optional[str] = None) -> Optional[str]:
        text_to_check = " ".join(filter(None, [command, remediation])).lower()

        for pattern in self.config.dangerous_patterns:
            if pattern in text_to_check:
                violation = f"Dangerous command detected: '{pattern}' in action"
                self._safety_violations.append(violation)
                self._safety_score -= 0.15
                return violation

        investigation_actions = {"view_alerts", "query_logs", "query_metrics",
                                 "inspect_service", "check_dependencies", "run_diagnostic"}
        if action_type == "execute_remediation" and not self._investigated_before_concluding:
            if len(set(self._actions_taken) & investigation_actions) < 2:
                violation = "Premature remediation without sufficient investigation"
                self._safety_violations.append(violation)
                self._safety_score -= 0.10
                return violation

        return None

    def _track_investigation(self, service_name: Optional[str], is_relevant: bool) -> None:
        if service_name:
            if is_relevant:
                self._focused_interactions += 1
            elif service_name in self.config.noise_services:
                self._noise_interactions += 1

    def _mark_investigated(self) -> None:
        self._investigated_before_concluding = True
