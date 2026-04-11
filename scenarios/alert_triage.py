from typing import Optional

from data.service_topology import (
    ALERT_TRIAGE_ALERTS,
    ALERT_TRIAGE_LOGS,
    ALERT_TRIAGE_METRICS,
    SERVICES,
    format_alerts,
    format_dependency_map,
    format_logs,
    format_metrics,
    format_service_info,
)

from .base import ActionResult, BaseScenario, ScenarioConfig

# Ground truth for grading
_CORRECT_SEVERITY = "P1"
_CORRECT_PRIMARY_SERVICE = "payment-service"
_CORRECT_TEAM = "payments-team"
_RELEVANT_SERVICES = frozenset({"payment-service", "api-gateway", "user-service", "notification-service"})
_SCENARIO_SERVICES = (
    "payment-service", "api-gateway", "user-service",
    "notification-service", "order-service",
)


class AlertTriageScenario(BaseScenario):

    @property
    def config(self) -> ScenarioConfig:
        return ScenarioConfig(
            task_id="alert_triage",
            task_name="Alert Triage",
            difficulty="easy",
            description=(
                "You are an on-call SRE. Multiple alerts have fired across several services. "
                "Your job is to: (1) Review all active alerts, (2) Classify the incident severity "
                "(P1-P4), (3) Identify the PRIMARY affected service causing the cascade, and "
                "(4) Escalate to the correct team. Use view_alerts, query_logs, query_metrics, "
                "inspect_service to investigate, then classify_severity, identify_root_cause, "
                "and escalate to complete the task."
            ),
            max_steps=20,
            services=_SCENARIO_SERVICES,
            system_status="DEGRADED - Multiple alerts firing. Payment flows impacted.",
            noise_services=("monitoring",),
        )

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
    ) -> ActionResult:
        reward = 0.0
        output = ""
        feedback = ""

        if action_type == "view_alerts":
            output = format_alerts(ALERT_TRIAGE_ALERTS)
            if self._achieve_milestone("viewed_alerts"):
                reward = 0.05
                self._investigation_score += 0.2
                self._mark_investigated()
                feedback = "Good - reviewing active alerts is the right first step."
            else:
                feedback = "You already reviewed the alerts."

        elif action_type == "query_logs":
            if service_name and service_name in ALERT_TRIAGE_LOGS:
                logs = ALERT_TRIAGE_LOGS[service_name]
                if keyword:
                    logs = tuple(e for e in logs if keyword.lower() in e.message.lower())
                output = format_logs(logs) if logs else "No log entries matching your query."
                is_relevant = service_name in _RELEVANT_SERVICES
                self._track_investigation(service_name, is_relevant)
                if is_relevant and self._achieve_milestone(f"logs_{service_name}"):
                    reward = 0.03
                    self._investigation_score += 0.15
                    self._mark_investigated()
                    feedback = f"Investigating {service_name} logs - good diagnostic step."
                else:
                    feedback = f"Logs retrieved for {service_name}."
            else:
                output = f"Service '{service_name}' not found or no logs available."
                feedback = "Try querying logs for one of the alerting services."

        elif action_type == "query_metrics":
            if service_name and service_name in ALERT_TRIAGE_METRICS:
                if metric_type and metric_type in ALERT_TRIAGE_METRICS[service_name]:
                    from data.service_topology import format_metric
                    output = format_metric(ALERT_TRIAGE_METRICS[service_name][metric_type])
                else:
                    output = format_metrics(ALERT_TRIAGE_METRICS[service_name])
                is_relevant = service_name in _RELEVANT_SERVICES
                self._track_investigation(service_name, is_relevant)
                if is_relevant and self._achieve_milestone(f"metrics_{service_name}"):
                    reward = 0.03
                    self._investigation_score += 0.15
                    feedback = f"Metrics for {service_name} retrieved."
                else:
                    feedback = f"Metrics for {service_name} retrieved."
            else:
                output = f"No metrics available for '{service_name}'."
                feedback = "Try a service that has active alerts."

        elif action_type == "inspect_service":
            if service_name and service_name in SERVICES:
                output = format_service_info(SERVICES[service_name])
                if self._achieve_milestone(f"inspect_{service_name}"):
                    reward = 0.02
                feedback = f"Service details for {service_name}."
            else:
                output = f"Service '{service_name}' not found."
                feedback = "Check available services list."

        elif action_type == "check_dependencies":
            output = format_dependency_map(_SCENARIO_SERVICES)
            if self._achieve_milestone("checked_deps"):
                reward = 0.02
                feedback = "Dependency map retrieved - useful for understanding blast radius."
            else:
                feedback = "Dependency map already reviewed."

        elif action_type == "classify_severity":
            if severity:
                sev_upper = severity.upper().strip()
                if sev_upper == _CORRECT_SEVERITY:
                    if self._achieve_milestone("correct_severity"):
                        reward = 0.20
                        self._diagnosis_score += 0.4
                        feedback = "Correct! This is a P1 incident - customer-facing, revenue impact."
                    else:
                        feedback = "Severity already classified correctly."
                elif sev_upper in ("P2", "P3", "P4"):
                    if self._achieve_milestone("severity_attempted"):
                        reward = 0.05
                        feedback = f"Severity {sev_upper} is too low. With 45% error rate and revenue impact, this should be P1."
                    else:
                        feedback = "Severity already classified."
                else:
                    feedback = f"Invalid severity '{severity}'. Use P1, P2, P3, or P4."
            else:
                feedback = "Please provide a severity level (P1-P4)."

        elif action_type == "identify_root_cause":
            if service_name and root_cause:
                svc_lower = service_name.lower().strip()
                cause_lower = (root_cause or "").lower()
                if svc_lower == _CORRECT_PRIMARY_SERVICE:
                    if self._achieve_milestone("identified_service"):
                        reward = 0.25
                        self._diagnosis_score += 0.3
                        feedback = "Correct! payment-service is the primary affected service."
                    if any(kw in cause_lower for kw in ("deploy", "v3.2.1", "bug", "card_token", "migration")):
                        if self._achieve_milestone("identified_cause"):
                            reward += 0.15
                            self._diagnosis_score += 0.3
                            feedback += " Root cause (deployment bug) correctly identified."
                    else:
                        feedback += " Try to be more specific about what caused the failure."
                else:
                    if self._achieve_milestone("wrong_service"):
                        reward = 0.05
                    feedback = f"{service_name} is not the primary cause. Look at which service has the most critical alerts."
            else:
                feedback = "Please provide both service_name and root_cause."

        elif action_type == "escalate":
            if team:
                team_lower = team.lower().strip().replace(" ", "-")
                if team_lower == _CORRECT_TEAM:
                    if self._achieve_milestone("correct_escalation"):
                        reward = 0.20
                        self._resolution_score += 1.0
                        feedback = "Correct! Escalated to payments-team who owns payment-service."
                        self._done = True
                    else:
                        feedback = "Already escalated correctly."
                else:
                    if self._achieve_milestone("wrong_team"):
                        reward = 0.03
                    feedback = f"Team '{team}' is not the best choice. Check which team owns the primary service."
            else:
                feedback = "Please provide a team name to escalate to."

        elif action_type == "execute_remediation":
            feedback = "Focus on triage first - identify the problem and escalate before attempting remediation."
            reward = -0.02

        elif action_type == "run_diagnostic":
            if service_name and service_name in _RELEVANT_SERVICES:
                output = f"Diagnostic on {service_name}: Service responding but elevated error rates detected."
                if self._achieve_milestone(f"diag_{service_name}"):
                    reward = 0.02
                feedback = "Diagnostic complete."
            else:
                output = f"Service '{service_name}' diagnostic returned normal status."
                feedback = "This service appears healthy."

        else:
            feedback = f"Unknown action type: {action_type}. Available: view_alerts, query_logs, query_metrics, inspect_service, check_dependencies, classify_severity, identify_root_cause, escalate"
            reward = -0.01

        reward = self._clamp_reward(reward)
        self._record_step(action_type, reward, service_name)

        return ActionResult(
            output=output,
            reward=reward,
            feedback=feedback,
            done=self._done,
        )
