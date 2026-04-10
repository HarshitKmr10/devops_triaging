"""
Procedural scenario generator.

Generates infinite novel incident scenarios from composable failure types,
service topologies, and cascade patterns. Seed-based for reproducibility.
"""

import random
from typing import Dict, List, Optional, Tuple

from data.service_topology import (
    SERVICES,
    Alert,
    LogEntry,
    MetricSnapshot,
    ServiceDefinition,
    format_alerts,
    format_dependency_map,
    format_logs,
    format_metrics,
    format_metric,
    format_service_info,
)
from scenarios.base import ActionResult, BaseScenario, ScenarioConfig

from .failure_types import FAILURE_REGISTRY, FailureType, GroundTruth


def _trace_dependents(service_name: str, depth: int) -> Tuple[str, ...]:
    """Find services that depend on the given service (reverse dependency trace)."""
    if depth <= 0:
        return ()

    dependents: list[str] = []
    for name, svc in SERVICES.items():
        if service_name in svc.dependencies and name not in dependents:
            dependents.append(name)

    result = list(dependents)
    for dep in dependents:
        for child in _trace_dependents(dep, depth - 1):
            if child not in result:
                result.append(child)

    return tuple(result)


# Services that can be primary failure sources (not databases/infra)
_CANDIDATE_PRIMARY_SERVICES = tuple(
    name for name, svc in SERVICES.items()
    if svc.port not in (5432, 5433, 5434, 6379, 5672, 443)
)


class GeneratedScenario(BaseScenario):
    """A procedurally generated incident scenario."""

    def __init__(
        self,
        failure: FailureType,
        primary_service: str,
        affected_services: Tuple[str, ...],
        alerts: Tuple[Alert, ...],
        logs: Dict[str, Tuple[LogEntry, ...]],
        metrics: Dict[str, Dict[str, MetricSnapshot]],
        ground_truth: GroundTruth,
        difficulty: str,
        seed: int,
        scenario_id: str,
    ) -> None:
        super().__init__()
        self._failure = failure
        self._primary_service = primary_service
        self._affected_services = affected_services
        self._alerts = alerts
        self._logs = logs
        self._metrics = metrics
        self._ground_truth = ground_truth
        self._difficulty = difficulty
        self._seed = seed
        self._scenario_id = scenario_id

        all_services = (primary_service,) + tuple(
            s for s in affected_services if s != primary_service
        )
        self._all_services = all_services
        self._relevant_services = frozenset(all_services)

    @property
    def config(self) -> ScenarioConfig:
        max_steps = {"easy": 15, "medium": 25, "hard": 30}.get(self._difficulty, 25)
        return ScenarioConfig(
            task_id=self._scenario_id,
            task_name=f"Generated: {self._failure.name} on {self._primary_service}",
            difficulty=self._difficulty,
            description=(
                f"You are an on-call SRE responding to a production incident. "
                f"Multiple services are affected. Investigate using alerts, logs, and metrics. "
                f"Identify the root cause, determine severity, and execute remediation. "
                f"Failure type hint: {self._failure.category}."
            ),
            max_steps=max_steps,
            services=self._all_services,
            system_status=f"DEGRADED - {self._failure.description}. Investigating.",
            noise_services=(),
        )

    @property
    def ground_truth(self) -> GroundTruth:
        return self._ground_truth

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
        reward = 0.0
        output = ""
        feedback = ""

        # Danger zone
        danger = self._check_danger_zone(action_type, command=command, remediation=remediation)
        if danger:
            feedback = f"DANGER: {danger}. Safety score reduced."
            reward = -0.05
            reward = self._clamp_reward(reward)
            self._record_step(action_type, reward, service_name)
            return ActionResult(output="", reward=reward, feedback=feedback)

        gt = self._ground_truth

        if action_type == "view_alerts":
            output = format_alerts(self._alerts)
            if self._achieve_milestone("viewed_alerts"):
                reward = 0.05
                self._investigation_score += 0.15
                self._mark_investigated()
                feedback = "Alerts reviewed. Identify the most critical service and investigate."
            else:
                feedback = "Alerts already reviewed."

        elif action_type == "query_logs":
            if service_name and service_name in self._logs:
                logs = self._logs[service_name]
                if keyword:
                    logs = tuple(e for e in logs if keyword.lower() in e.message.lower())
                output = format_logs(logs) if logs else "No matching log entries."

                is_relevant = service_name in self._relevant_services
                self._track_investigation(service_name, is_relevant)

                if is_relevant and self._achieve_milestone(f"logs_{service_name}"):
                    if service_name == self._primary_service:
                        reward = 0.08
                        self._investigation_score += 0.25
                    else:
                        reward = 0.04
                        self._investigation_score += 0.1
                    self._mark_investigated()
                    feedback = f"Logs for {service_name} retrieved."
                else:
                    feedback = f"Logs for {service_name}."
            else:
                output = f"No logs available for '{service_name}'."
                feedback = f"Available services: {', '.join(self._all_services)}"

        elif action_type == "query_metrics":
            if service_name and service_name in self._metrics:
                if metric_type and metric_type in self._metrics[service_name]:
                    output = format_metric(self._metrics[service_name][metric_type])
                else:
                    output = format_metrics(self._metrics[service_name])

                is_relevant = service_name in self._relevant_services
                self._track_investigation(service_name, is_relevant)

                if is_relevant and self._achieve_milestone(f"metrics_{service_name}"):
                    reward = 0.05
                    self._investigation_score += 0.15
                    feedback = f"Metrics for {service_name} show anomalies."
                else:
                    feedback = f"Metrics for {service_name}."
            else:
                output = f"No metrics for '{service_name}'."
                feedback = "Try one of the affected services."

        elif action_type == "inspect_service":
            if service_name and service_name in SERVICES:
                output = format_service_info(SERVICES[service_name])
                if self._achieve_milestone(f"inspect_{service_name}"):
                    reward = 0.02
                    self._investigation_score += 0.05
                feedback = f"Service info for {service_name}."
            else:
                output = f"Service '{service_name}' not found."

        elif action_type == "check_dependencies":
            output = format_dependency_map(self._all_services)
            if self._achieve_milestone("checked_deps"):
                reward = 0.03
                self._investigation_score += 0.1
                feedback = "Dependency map retrieved."
            else:
                feedback = "Already reviewed."

        elif action_type == "run_diagnostic":
            if service_name and service_name in self._relevant_services:
                if service_name == self._primary_service:
                    output = (
                        f"Diagnostic: {service_name}\n"
                        f"  Status: DEGRADED\n"
                        f"  Failure Type: {self._failure.category}\n"
                        f"  Description: {self._failure.description}\n"
                        f"  Impact: {len(self._affected_services)} services affected"
                    )
                    if self._achieve_milestone(f"diag_{service_name}"):
                        reward = 0.06
                        self._investigation_score += 0.15
                        feedback = f"Key diagnostic data from {service_name}."
                else:
                    output = f"Diagnostic: {service_name}\n  Status: DEGRADED (upstream dependency issue)"
                    if self._achieve_milestone(f"diag_{service_name}"):
                        reward = 0.02
                    feedback = f"{service_name} affected by upstream failure."
            else:
                output = f"Diagnostic: {service_name} - normal."
                feedback = "This service is not directly affected."

        elif action_type == "classify_severity":
            if severity:
                sev = severity.upper().strip()
                if sev == gt.correct_severity:
                    if self._achieve_milestone("correct_severity"):
                        reward = 0.05
                        self._diagnosis_score += 0.2
                        feedback = f"Correct severity: {sev}."
                else:
                    feedback = f"{sev} may not match the actual impact level."

        elif action_type == "identify_root_cause":
            if root_cause and service_name:
                cause_lower = root_cause.lower()
                svc_lower = service_name.lower()
                matches = sum(1 for kw in gt.root_cause_keywords if kw in cause_lower or kw in svc_lower)

                if svc_lower == gt.root_cause_service and matches >= 2:
                    if self._achieve_milestone("correct_root_cause"):
                        reward = 0.25
                        self._diagnosis_score += 0.8
                        feedback = f"Correct! Root cause identified on {service_name}."
                elif svc_lower == gt.root_cause_service:
                    if self._achieve_milestone("partial_root_cause"):
                        reward = 0.10
                        self._diagnosis_score += 0.3
                        feedback = "Right service, but be more specific about the cause."
                else:
                    feedback = "Not the root cause service. Keep investigating."
            else:
                feedback = "Provide both service_name and root_cause."

        elif action_type == "execute_remediation":
            if remediation:
                rem_lower = remediation.lower()
                svc_lower = (service_name or "").lower()
                matches = sum(1 for kw in gt.remediation_keywords if kw in rem_lower)
                targets_correct = svc_lower == gt.root_cause_service or gt.root_cause_service in rem_lower

                if matches >= 1 and targets_correct:
                    if self._achieve_milestone("correct_remediation"):
                        reward = 0.20
                        self._resolution_score += 1.0
                        feedback = f"Correct remediation applied to {gt.root_cause_service}."
                        self._done = True
                elif matches >= 1:
                    if self._achieve_milestone("wrong_target"):
                        reward = 0.05
                    feedback = f"Right approach but wrong target. Apply to {gt.root_cause_service}."
                else:
                    feedback = "This remediation doesn't address the root cause."
            else:
                feedback = "Provide a remediation description."

        elif action_type == "escalate":
            if team:
                team_lower = team.lower().strip().replace(" ", "-")
                if team_lower == gt.correct_team:
                    if self._achieve_milestone("correct_escalation"):
                        reward = 0.05
                        self._resolution_score += 0.3
                        feedback = f"Correctly escalated to {team}."
                else:
                    feedback = f"{team} may not be the best team for this."
            else:
                feedback = "Provide a team name."

        else:
            feedback = f"Unknown action: {action_type}"
            reward = -0.01

        reward = self._clamp_reward(reward)
        self._record_step(action_type, reward, service_name)

        return ActionResult(
            output=output,
            reward=reward,
            feedback=feedback,
            done=self._done,
        )


class ScenarioGenerator:
    """
    Generates novel incident scenarios from composable building blocks.

    Usage:
        gen = ScenarioGenerator()
        scenario = gen.generate(seed=42, difficulty="medium")
        obs = scenario.handle_action("view_alerts")
    """

    def __init__(
        self,
        failure_types: Optional[Dict[str, FailureType]] = None,
    ) -> None:
        self._failure_types = failure_types or FAILURE_REGISTRY

    def generate(
        self,
        seed: int = 42,
        difficulty: str = "medium",
        failure_type: Optional[str] = None,
        primary_service: Optional[str] = None,
    ) -> GeneratedScenario:
        """Generate a new scenario.

        Args:
            seed: Random seed for reproducibility
            difficulty: easy/medium/hard — controls cascade depth
            failure_type: Specific failure type name, or None for random
            primary_service: Specific service, or None for random

        Returns:
            A fully initialized GeneratedScenario ready for reset/step
        """
        rng = random.Random(seed)

        # Pick failure type
        if failure_type and failure_type in self._failure_types:
            failure = self._failure_types[failure_type]
        else:
            failure = rng.choice(list(self._failure_types.values()))

        # Pick primary service
        if primary_service and primary_service in SERVICES:
            primary = primary_service
        else:
            primary = rng.choice(_CANDIDATE_PRIMARY_SERVICES)

        # Determine cascade depth based on difficulty
        cascade_depth = {"easy": 0, "medium": 1, "hard": 3}.get(difficulty, 1)
        dependents = _trace_dependents(primary, cascade_depth)
        affected = (primary,) + dependents

        # Generate data
        alerts = failure.generate_alerts(primary, affected, rng)
        logs = failure.generate_logs(primary, affected, rng)
        metrics = failure.generate_metrics(primary, affected, rng)
        ground_truth = failure.get_ground_truth(primary, cascade_chain=affected)

        scenario_id = f"gen_{failure.name}_{primary}_{seed}"

        return GeneratedScenario(
            failure=failure,
            primary_service=primary,
            affected_services=affected,
            alerts=alerts,
            logs=logs,
            metrics=metrics,
            ground_truth=ground_truth,
            difficulty=difficulty,
            seed=seed,
            scenario_id=scenario_id,
        )

    def generate_batch(
        self,
        count: int = 10,
        base_seed: int = 0,
        difficulty: str = "medium",
    ) -> List[GeneratedScenario]:
        """Generate a batch of diverse scenarios."""
        return [
            self.generate(seed=base_seed + i, difficulty=difficulty)
            for i in range(count)
        ]
