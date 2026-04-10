"""
Runbook-to-Scenario converter.

Takes a markdown runbook as input and generates a BaseScenario
with appropriate alerts, logs, metrics, and grading criteria.

Can work with:
- Plain text/markdown runbooks
- LLM-assisted parsing for complex runbooks
- Template-based generation for structured runbooks
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from data.service_topology import (
    Alert, LogEntry, MetricSnapshot, SERVICES,
    format_alerts, format_logs, format_metrics, format_service_info,
    format_dependency_map, format_metric,
)
from scenarios.base import ActionResult, BaseScenario, ScenarioConfig


@dataclass
class RunbookStep:
    """A parsed step from a runbook."""

    step_number: int
    action: str  # What to do (e.g., "Check CPU usage on payment-service")
    expected_finding: str  # What you should see (e.g., "CPU > 80%")
    action_type: str  # Mapped to our action types
    service_name: Optional[str] = None
    keywords: List[str] = field(default_factory=list)


@dataclass
class ParsedRunbook:
    """A fully parsed runbook ready for scenario generation."""

    title: str
    description: str
    trigger_condition: str
    severity: str
    primary_service: str
    affected_services: List[str]
    team: str
    steps: List[RunbookStep]
    root_cause_keywords: List[str]
    remediation_description: str
    remediation_keywords: List[str]


def parse_runbook_markdown(content: str) -> ParsedRunbook:
    """Parse a structured markdown runbook into a ParsedRunbook.

    Expected format:
    ```
    # Runbook: <title>

    ## Trigger
    <when this runbook applies>

    ## Severity: P1/P2/P3/P4

    ## Services
    - Primary: <service>
    - Affected: <service1>, <service2>
    - Team: <team-name>

    ## Investigation Steps
    1. <action> -> Expect: <finding>
    2. <action> -> Expect: <finding>

    ## Root Cause
    Keywords: <keyword1>, <keyword2>

    ## Remediation
    <what to do to fix it>
    Keywords: <keyword1>, <keyword2>
    ```
    """
    lines = content.strip().split("\n")

    title = ""
    description = ""
    trigger = ""
    severity = "P2"
    primary_service = ""
    affected: List[str] = []
    team = ""
    steps: List[RunbookStep] = []
    root_cause_kw: List[str] = []
    remediation_desc = ""
    remediation_kw: List[str] = []

    current_section = ""
    step_counter = 0

    for line in lines:
        stripped = line.strip()

        # Section headers
        if stripped.startswith("# Runbook:"):
            title = stripped.replace("# Runbook:", "").strip()
            continue
        if stripped.startswith("## "):
            current_section = stripped[3:].strip().lower()
            if current_section.startswith("severity"):
                match = re.search(r"P[1-4]", stripped)
                if match:
                    severity = match.group()
            continue

        if not stripped:
            continue

        if current_section == "trigger":
            trigger += stripped + " "

        elif current_section == "services":
            if stripped.lower().startswith("- primary:"):
                primary_service = stripped.split(":", 1)[1].strip()
            elif stripped.lower().startswith("- affected:"):
                affected = [s.strip() for s in stripped.split(":", 1)[1].split(",")]
            elif stripped.lower().startswith("- team:"):
                team = stripped.split(":", 1)[1].strip()

        elif current_section == "investigation steps":
            # Parse "1. Check logs on payment-service -> Expect: connection errors"
            match = re.match(r"\d+\.\s*(.+?)(?:\s*->\s*Expect:\s*(.+))?$", stripped)
            if match:
                step_counter += 1
                action_text = match.group(1).strip()
                expected = match.group(2).strip() if match.group(2) else ""

                # Map natural language to action types
                action_type, svc = _map_action(action_text)

                steps.append(RunbookStep(
                    step_number=step_counter,
                    action=action_text,
                    expected_finding=expected,
                    action_type=action_type,
                    service_name=svc or primary_service,
                    keywords=_extract_keywords(action_text + " " + expected),
                ))

        elif current_section == "root cause":
            if stripped.lower().startswith("keywords:"):
                root_cause_kw = [k.strip() for k in stripped.split(":", 1)[1].split(",")]
            else:
                description += stripped + " "

        elif current_section == "remediation":
            if stripped.lower().startswith("keywords:"):
                remediation_kw = [k.strip() for k in stripped.split(":", 1)[1].split(",")]
            else:
                remediation_desc += stripped + " "

    if not affected:
        affected = [primary_service]

    return ParsedRunbook(
        title=title,
        description=description.strip() or trigger.strip(),
        trigger_condition=trigger.strip(),
        severity=severity,
        primary_service=primary_service,
        affected_services=affected,
        team=team,
        steps=steps,
        root_cause_keywords=root_cause_kw,
        remediation_description=remediation_desc.strip(),
        remediation_keywords=remediation_kw,
    )


def _map_action(text: str) -> Tuple[str, Optional[str]]:
    """Map natural language action to our action_type + service_name."""
    text_lower = text.lower()

    # Extract service name if mentioned
    service = None
    for svc_name in SERVICES:
        if svc_name in text_lower:
            service = svc_name
            break

    # Map to action types
    if any(kw in text_lower for kw in ["alert", "monitor", "check alert"]):
        return "view_alerts", service
    elif any(kw in text_lower for kw in ["log", "check log", "search log"]):
        return "query_logs", service
    elif any(kw in text_lower for kw in ["metric", "cpu", "memory", "latency", "error rate"]):
        return "query_metrics", service
    elif any(kw in text_lower for kw in ["inspect", "service detail", "config"]):
        return "inspect_service", service
    elif any(kw in text_lower for kw in ["dependency", "depend", "upstream", "downstream"]):
        return "check_dependencies", service
    elif any(kw in text_lower for kw in ["diagnostic", "diagnose", "health check"]):
        return "run_diagnostic", service
    elif any(kw in text_lower for kw in ["severity", "classify", "priority"]):
        return "classify_severity", service
    elif any(kw in text_lower for kw in ["root cause", "identify cause"]):
        return "identify_root_cause", service
    elif any(kw in text_lower for kw in ["fix", "remediate", "rollback", "restart", "resolve"]):
        return "execute_remediation", service
    elif any(kw in text_lower for kw in ["escalate", "notify", "page"]):
        return "escalate", service

    return "query_logs", service


def _extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text."""
    stop_words = {"the", "a", "an", "is", "are", "on", "in", "for", "to", "of", "and", "or", "check", "should", "see"}
    words = re.findall(r'\b\w+\b', text.lower())
    return [w for w in words if w not in stop_words and len(w) > 2]


class RunbookScenario(BaseScenario):
    """A scenario generated from a parsed runbook."""

    def __init__(self, runbook: ParsedRunbook) -> None:
        super().__init__()
        self._runbook = runbook
        self._step_map: Dict[str, RunbookStep] = {}
        for step in runbook.steps:
            key = f"{step.action_type}_{step.service_name or 'any'}"
            self._step_map[key] = step

        # Generate synthetic data from runbook
        self._alerts = self._generate_alerts()
        self._logs = self._generate_logs()
        self._metrics = self._generate_metrics()

    @property
    def config(self) -> ScenarioConfig:
        return ScenarioConfig(
            task_id=f"runbook_{self._runbook.title.lower().replace(' ', '_')[:30]}",
            task_name=f"Runbook: {self._runbook.title}",
            difficulty="medium",
            description=(
                f"Follow the runbook for: {self._runbook.title}. "
                f"Trigger: {self._runbook.trigger_condition} "
                f"Investigate the {self._runbook.primary_service} and related services. "
                f"Identify the root cause and execute the documented remediation."
            ),
            max_steps=max(20, len(self._runbook.steps) * 3),
            services=tuple(self._runbook.affected_services),
            system_status=f"INCIDENT - {self._runbook.trigger_condition}",
        )

    def _generate_alerts(self) -> Tuple[Alert, ...]:
        """Generate synthetic alerts from runbook context."""
        alerts = [
            Alert(
                alert_id=f"RB-{i:03d}",
                severity="CRITICAL" if i == 0 else "WARNING",
                service=self._runbook.primary_service,
                title=f"{self._runbook.title} - Alert {i + 1}",
                description=step.expected_finding or step.action,
                timestamp=f"2024-03-15T14:{20 + i}:00Z",
            )
            for i, step in enumerate(self._runbook.steps[:3])
        ]
        return tuple(alerts)

    def _generate_logs(self) -> Dict[str, Tuple[LogEntry, ...]]:
        """Generate synthetic log entries from runbook steps."""
        logs: Dict[str, List[LogEntry]] = {}
        for step in self._runbook.steps:
            svc = step.service_name or self._runbook.primary_service
            if svc not in logs:
                logs[svc] = []
            logs[svc].append(LogEntry(
                timestamp=f"2024-03-15T14:{20 + step.step_number}:00Z",
                level="ERROR" if "error" in step.expected_finding.lower() else "WARN",
                service=svc,
                message=step.expected_finding or f"Issue detected: {step.action}",
            ))
        return {k: tuple(v) for k, v in logs.items()}

    def _generate_metrics(self) -> Dict[str, Dict[str, MetricSnapshot]]:
        """Generate synthetic metrics from runbook context."""
        metrics: Dict[str, Dict[str, MetricSnapshot]] = {}
        svc_def = SERVICES.get(self._runbook.primary_service)
        if svc_def:
            metrics[self._runbook.primary_service] = {
                "error_rate": MetricSnapshot(
                    self._runbook.primary_service, "error_rate",
                    45.0, svc_def.normal_error_rate * 100, "%",
                    "2024-03-15T14:25:00Z", "spike",
                ),
                "latency": MetricSnapshot(
                    self._runbook.primary_service, "latency",
                    float(svc_def.normal_latency_ms * 10), float(svc_def.normal_latency_ms),
                    "ms", "2024-03-15T14:25:00Z", "spike",
                ),
            }
        return metrics

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
        rb = self._runbook

        # Danger zone
        danger = self._check_danger_zone(action_type, command=command, remediation=remediation)
        if danger:
            reward = self._clamp_reward(-0.05)
            self._record_step(action_type, reward, service_name)
            return ActionResult(output="", reward=reward, feedback=f"DANGER: {danger}", done=False)

        # Check if this action matches a runbook step
        key = f"{action_type}_{service_name or 'any'}"
        matched_step = self._step_map.get(key)

        if action_type == "view_alerts":
            output = format_alerts(self._alerts)
            if self._achieve_milestone("viewed_alerts"):
                reward = 0.05
                self._investigation_score += 0.2
                self._mark_investigated()
                feedback = "Alerts reviewed."

        elif action_type == "query_logs":
            svc = service_name or rb.primary_service
            if svc in self._logs:
                logs = self._logs[svc]
                if keyword:
                    logs = tuple(e for e in logs if keyword.lower() in e.message.lower())
                output = format_logs(logs) if logs else "No matching entries."
                if self._achieve_milestone(f"logs_{svc}"):
                    reward = 0.05
                    self._investigation_score += 0.15
                    self._mark_investigated()
                    if matched_step:
                        feedback = f"Runbook step {matched_step.step_number}: {matched_step.expected_finding}"
                    else:
                        feedback = f"Logs for {svc}."
            else:
                output = f"No logs for '{svc}'."
                feedback = f"Try: {', '.join(self._logs.keys())}"

        elif action_type == "query_metrics":
            svc = service_name or rb.primary_service
            if svc in self._metrics:
                output = format_metrics(self._metrics[svc])
                if self._achieve_milestone(f"metrics_{svc}"):
                    reward = 0.05
                    self._investigation_score += 0.15
                    feedback = f"Metrics for {svc}."
            else:
                output = f"No metrics for '{svc}'."

        elif action_type == "inspect_service":
            if service_name and service_name in SERVICES:
                output = format_service_info(SERVICES[service_name])
                if self._achieve_milestone(f"inspect_{service_name}"):
                    reward = 0.02
                    self._investigation_score += 0.05

        elif action_type == "check_dependencies":
            output = format_dependency_map(tuple(rb.affected_services))
            if self._achieve_milestone("deps"):
                reward = 0.03
                self._investigation_score += 0.1

        elif action_type == "run_diagnostic":
            svc = service_name or rb.primary_service
            if matched_step:
                output = f"Diagnostic ({svc}): {matched_step.expected_finding}"
                if self._achieve_milestone(f"diag_{svc}"):
                    reward = 0.05
                    self._investigation_score += 0.1
            else:
                output = f"Diagnostic ({svc}): No specific issues found."

        elif action_type == "classify_severity":
            if severity and severity.upper() == rb.severity:
                if self._achieve_milestone("severity"):
                    reward = 0.05
                    self._diagnosis_score += 0.2
                    feedback = f"Correct: {rb.severity}."

        elif action_type == "identify_root_cause":
            if root_cause:
                cause_lower = root_cause.lower()
                matches = sum(1 for kw in rb.root_cause_keywords if kw.lower() in cause_lower)
                svc_match = (service_name or "").lower() == rb.primary_service.lower()
                if matches >= 2 and svc_match:
                    if self._achieve_milestone("root_cause"):
                        reward = 0.20
                        self._diagnosis_score += 0.8
                        feedback = "Root cause correctly identified per runbook."
                elif matches >= 1:
                    if self._achieve_milestone("partial_cause"):
                        reward = 0.08
                        self._diagnosis_score += 0.3
                        feedback = "Partially correct. Check runbook for more specifics."

        elif action_type == "execute_remediation":
            if remediation:
                rem_lower = remediation.lower()
                matches = sum(1 for kw in rb.remediation_keywords if kw.lower() in rem_lower)
                if matches >= 1:
                    if self._achieve_milestone("remediation"):
                        reward = 0.20
                        self._resolution_score += 1.0
                        feedback = "Remediation matches runbook procedure."
                        self._done = True
                else:
                    feedback = "Remediation doesn't match the documented procedure."

        elif action_type == "escalate":
            if team and team.lower().replace(" ", "-") == rb.team.lower().replace(" ", "-"):
                if self._achieve_milestone("escalated"):
                    reward = 0.05
                    self._resolution_score += 0.3
                    feedback = f"Correctly escalated to {rb.team}."

        else:
            feedback = f"Unknown action: {action_type}"

        if not feedback:
            feedback = f"Action {action_type} executed."

        reward = self._clamp_reward(reward)
        self._record_step(action_type, reward, service_name)
        return ActionResult(output=output, reward=reward, feedback=feedback, done=self._done)


def convert_runbook(markdown_content: str) -> RunbookScenario:
    """Convert a markdown runbook into a graded scenario.

    Args:
        markdown_content: The runbook in markdown format

    Returns:
        A RunbookScenario ready for use with the environment
    """
    parsed = parse_runbook_markdown(markdown_content)
    return RunbookScenario(parsed)
