"""
Base scenario class for all incident response scenarios.

Each scenario defines the incident data, valid actions, grading logic,
and reward shaping for a specific type of SRE incident.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class ActionResult:
    """Immutable result of processing an agent action."""

    output: str
    reward: float
    feedback: str
    done: bool = False


@dataclass
class ScenarioConfig:
    """Configuration for a scenario."""

    task_id: str
    task_name: str
    difficulty: str
    description: str
    max_steps: int
    services: Tuple[str, ...]
    system_status: str


class BaseScenario(ABC):
    """Abstract base class for all incident response scenarios."""

    def __init__(self) -> None:
        self._step_count: int = 0
        self._total_reward: float = 0.0
        self._actions_taken: List[str] = []
        self._services_investigated: Set[str] = set()
        self._milestones_achieved: Set[str] = set()
        self._done: bool = False

    @property
    @abstractmethod
    def config(self) -> ScenarioConfig:
        """Return the scenario configuration."""
        ...

    @abstractmethod
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
        """Process an agent action and return the result with reward."""
        ...

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

    def _record_step(self, action_type: str, reward: float, service_name: Optional[str] = None) -> None:
        """Record a step and update tracking state."""
        self._step_count += 1
        self._total_reward += reward
        self._actions_taken.append(action_type)
        if service_name:
            self._services_investigated.add(service_name)
        if self._step_count >= self.config.max_steps:
            self._done = True

    def _achieve_milestone(self, milestone: str) -> bool:
        """Mark a milestone as achieved. Returns True if it was newly achieved."""
        if milestone in self._milestones_achieved:
            return False
        self._milestones_achieved.add(milestone)
        return True

    def _clamp_reward(self, reward: float) -> float:
        """Ensure total reward stays in [0.0, 1.0] range."""
        remaining = 1.0 - self._total_reward
        return max(0.0, min(reward, remaining))
