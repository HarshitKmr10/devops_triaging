"""
Task 3: Cascading Failure (Hard)

The agent must trace a multi-service cascading failure backwards to its source:
auth-service config deployment -> api-gateway 401s -> user-service auth failures
-> order-service failures -> payment-service transaction failures

Scenario: A config deployment to auth-service changed the JWT key_id format
from 'rsa-prod-2024' (hyphenated) to 'rsa_prod_2024' (underscore), causing
95% of valid tokens to be rejected.
"""

from typing import Optional

from data.service_topology import (
    CASCADE_ALERTS,
    CASCADE_LOGS,
    CASCADE_METRICS,
    SERVICES,
    format_alerts,
    format_dependency_map,
    format_logs,
    format_metrics,
    format_service_info,
)

from .base import ActionResult, BaseScenario, ScenarioConfig

# Ground truth
_ROOT_CAUSE_SERVICE = "auth-service"
_ROOT_CAUSE_KEYWORDS = frozenset({
    "config", "jwt", "key_id", "key id", "validation", "deployment",
    "jwt-validation-v3", "underscore", "format", "rsa",
})
_REMEDIATION_KEYWORDS = frozenset({
    "rollback", "revert", "restore", "previous config", "undo",
    "jwt-validation-v2", "old config", "remove config",
})
_CASCADE_CHAIN = ("auth-service", "api-gateway", "user-service", "order-service", "payment-service")
_ALL_SERVICES = (
    "auth-service", "api-gateway", "user-service",
    "order-service", "payment-service", "notification-service",
)


class CascadingFailureScenario(BaseScenario):
    """Hard scenario: trace a cascading failure back to its root cause."""

    def __init__(self) -> None:
        super().__init__()
        self._cascade_traced: list[str] = []

    @property
    def config(self) -> ScenarioConfig:
        return ScenarioConfig(
            task_id="cascading_failure",
            task_name="Cascading Failure",
            difficulty="hard",
            description=(
                "You are an on-call SRE responding to a major outage. Multiple services are failing "
                "in what appears to be a cascading failure. Payment processing is down, orders are "
                "failing, and user authentication is broken. Your job is to: (1) Investigate the "
                "symptoms across all services, (2) Trace the failure cascade back to its root cause, "
                "(3) Identify the specific change that triggered the cascade, and (4) Execute the "
                "correct remediation to restore service. Start from the most visible symptoms and "
                "work backwards through the dependency chain."
            ),
            max_steps=30,
            services=_ALL_SERVICES,
            system_status="MAJOR OUTAGE - Multiple services failing. Revenue impact: ~$120K/hour.",
            noise_services=("notification-service",),
        )

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

        # Danger zone check
        danger = self._check_danger_zone(action_type, command=command, remediation=remediation)
        if danger:
            feedback = f"DANGER: {danger}. Safety score reduced."
            reward = -0.05
            reward = self._clamp_reward(reward)
            self._record_step(action_type, reward, service_name)
            return ActionResult(output="", reward=reward, feedback=feedback)

        if action_type == "view_alerts":
            output = format_alerts(CASCADE_ALERTS)
            if self._achieve_milestone("viewed_alerts"):
                reward = 0.03
                self._investigation_score += 0.1
                self._mark_investigated()
                feedback = (
                    "Multiple services affected. Notice the timestamps - which alerts came first? "
                    "The auth-service config update was earliest at 14:00:15Z."
                )
            else:
                feedback = "Alerts already reviewed."

        elif action_type == "query_logs":
            if service_name and service_name in CASCADE_LOGS:
                logs = CASCADE_LOGS[service_name]
                if keyword:
                    logs = tuple(e for e in logs if keyword.lower() in e.message.lower())
                output = format_logs(logs) if logs else "No log entries matching your query."

                # Track cascade tracing
                if service_name in _CASCADE_CHAIN and service_name not in self._cascade_traced:
                    self._cascade_traced.append(service_name)

                self._track_investigation(service_name, service_name in _CASCADE_CHAIN)

                if service_name == "auth-service" and self._achieve_milestone("logs_auth_service"):
                    reward = 0.10
                    self._investigation_score += 0.3
                    self._mark_investigated()
                    feedback = (
                        "CRITICAL FINDING: auth-service logs show config deployment jwt-validation-v3 "
                        "changed key_id format. 95% of tokens being rejected!"
                    )
                elif service_name == "api-gateway" and self._achieve_milestone("logs_api_gateway"):
                    reward = 0.04
                    feedback = "api-gateway shows 401 spike from auth-service. The auth layer is rejecting tokens."
                elif service_name == "user-service" and self._achieve_milestone("logs_user_service"):
                    reward = 0.04
                    feedback = "user-service can't authenticate - auth-service is rejecting valid tokens."
                elif service_name == "order-service" and self._achieve_milestone("logs_order_service"):
                    reward = 0.03
                    feedback = "order-service failing because user-service can't verify identity."
                elif service_name == "payment-service" and self._achieve_milestone("logs_payment_service"):
                    reward = 0.03
                    feedback = "payment-service is a downstream victim. Trace the chain upstream."
                elif self._achieve_milestone(f"logs_{service_name}"):
                    reward = 0.01
                    feedback = f"Logs for {service_name} retrieved."
                else:
                    feedback = f"Already reviewed logs for {service_name}."
            else:
                output = f"Service '{service_name}' not found or no logs available."
                feedback = f"Try one of: {', '.join(_ALL_SERVICES)}"

        elif action_type == "query_metrics":
            if service_name and service_name in CASCADE_METRICS:
                if metric_type and metric_type in CASCADE_METRICS[service_name]:
                    from data.service_topology import format_metric
                    output = format_metric(CASCADE_METRICS[service_name][metric_type])
                else:
                    output = format_metrics(CASCADE_METRICS[service_name])

                if service_name == "auth-service" and self._achieve_milestone("metrics_auth"):
                    reward = 0.05
                    feedback = (
                        "Interesting: auth-service error rate is 95% but CPU/latency are NORMAL. "
                        "This isn't a resource problem - it's a logic/config problem."
                    )
                elif service_name in _CASCADE_CHAIN and self._achieve_milestone(f"metrics_{service_name}"):
                    reward = 0.02
                    feedback = f"{service_name} metrics show degradation consistent with upstream failures."
                else:
                    feedback = f"Metrics for {service_name} retrieved."
            else:
                output = f"No metrics available for '{service_name}'."
                feedback = "Check available services."

        elif action_type == "inspect_service":
            if service_name and service_name in SERVICES:
                output = format_service_info(SERVICES[service_name])
                if service_name == "auth-service" and self._achieve_milestone("inspect_auth"):
                    reward = 0.03
                    feedback = "auth-service has no dependencies except redis-cache. It's at the top of the chain."
                elif self._achieve_milestone(f"inspect_{service_name}"):
                    reward = 0.01
                feedback = feedback or f"Service details for {service_name}."
            else:
                output = f"Service '{service_name}' not found."
                feedback = "Check available services."

        elif action_type == "check_dependencies":
            output = format_dependency_map(_ALL_SERVICES)
            if self._achieve_milestone("checked_deps"):
                reward = 0.05
                feedback = (
                    "Dependency map reveals the cascade path: auth-service is depended on by "
                    "api-gateway and user-service. A failure there cascades through everything."
                )
            else:
                feedback = "Dependencies already reviewed."

        elif action_type == "run_diagnostic":
            if service_name == "auth-service":
                output = (
                    "Diagnostic: auth-service\n"
                    "  Status: RUNNING (not crashed)\n"
                    "  CPU: 22% (normal)\n"
                    "  Memory: 35% (normal)\n"
                    "  Latency: 25ms (normal)\n"
                    "  Token Rejection Rate: 95%\n"
                    "  Last Config Change: jwt-validation-v3 at 14:00:15Z\n"
                    "  Config Diff: key_id format changed from 'rsa-prod-2024' to 'rsa_prod_2024'\n"
                    "  Active JWT Keys in New Config: ['rsa_prod_2024']\n"
                    "  Tokens in Circulation Using: 'rsa-prod-2024' (hyphenated format)"
                )
                if self._achieve_milestone("diag_auth"):
                    reward = 0.08
                    feedback = (
                        "SMOKING GUN: Config diff shows key_id format change. Tokens use hyphens "
                        "but new config expects underscores."
                    )
            elif service_name and service_name in _CASCADE_CHAIN:
                output = f"Diagnostic: {service_name}\n  Status: DEGRADED\n  Errors caused by upstream auth failures."
                if self._achieve_milestone(f"diag_{service_name}"):
                    reward = 0.02
                feedback = f"{service_name} is a downstream victim of the auth failure."
            else:
                output = f"Diagnostic on {service_name}: Status normal."
                feedback = "This service is not directly affected."

        elif action_type == "classify_severity":
            if severity and severity.upper() == "P1":
                if self._achieve_milestone("classified_p1"):
                    reward = 0.03
                    feedback = "Correct - P1. Multiple services down, revenue impact."
            else:
                feedback = "With this level of impact, this should be P1."

        elif action_type == "identify_root_cause":
            if root_cause:
                cause_lower = root_cause.lower()
                svc = (service_name or "").lower()

                matches = sum(1 for kw in _ROOT_CAUSE_KEYWORDS if kw in cause_lower)

                identified_auth = svc == "auth-service" or "auth" in cause_lower
                identified_config = any(kw in cause_lower for kw in ("config", "jwt-validation", "deployment", "key_id"))

                if identified_auth and identified_config and matches >= 3:
                    if self._achieve_milestone("correct_root_cause"):
                        reward = 0.20
                        self._diagnosis_score += 1.0
                        feedback = (
                            "Excellent! Root cause correctly identified: auth-service config "
                            "deployment jwt-validation-v3 changed key_id format, causing 95% "
                            "token rejection and cascading failures."
                        )
                elif identified_auth and matches >= 1:
                    if self._achieve_milestone("partial_root_cause"):
                        reward = 0.08
                        feedback = (
                            "You correctly identified auth-service. Be more specific about "
                            "what changed - look at the config deployment and key_id format."
                        )
                else:
                    if not self._milestones_achieved & {"correct_root_cause", "partial_root_cause"}:
                        reward = 0.02
                    feedback = (
                        "Not quite. Trace the cascade backwards - which service's failure caused "
                        "all the others? Look at alert timestamps and dependency chain."
                    )
            else:
                feedback = "Please provide root_cause description."

        elif action_type == "execute_remediation":
            if remediation:
                rem_lower = remediation.lower()
                matches = sum(1 for kw in _REMEDIATION_KEYWORDS if kw in rem_lower)
                targets_auth = "auth" in rem_lower or (service_name or "").lower() == "auth-service"

                if matches >= 1 and targets_auth:
                    if self._achieve_milestone("correct_remediation"):
                        self._resolution_score += 1.0
                        # Bonus for tracing the full cascade
                        chain_bonus = 0.0
                        traced_count = len(set(self._cascade_traced) & set(_CASCADE_CHAIN))
                        if traced_count >= 4:
                            chain_bonus = 0.05
                            feedback_extra = " Bonus: you traced the full cascade chain!"
                        elif traced_count >= 3:
                            chain_bonus = 0.03
                            feedback_extra = " Good cascade tracing."
                        else:
                            feedback_extra = ""

                        reward = 0.20 + chain_bonus
                        feedback = (
                            "Correct remediation! Rolling back auth-service config to the previous "
                            "version will restore JWT validation and unblock the entire cascade."
                            + feedback_extra
                        )
                        self._done = True
                elif matches >= 1:
                    if self._achieve_milestone("wrong_target_remediation"):
                        reward = 0.05
                    feedback = (
                        "Right idea (rollback/revert) but wrong target. The root cause is in "
                        "auth-service - remediate there."
                    )
                else:
                    feedback = (
                        "This won't fix the cascading failure. The auth-service config needs "
                        "to be rolled back to restore JWT validation."
                    )
            else:
                feedback = "Please provide a remediation action."

        elif action_type == "escalate":
            if team:
                if self._achieve_milestone("escalated"):
                    reward = 0.02
                feedback = f"Escalated to {team}. Continue investigating to find the root cause."

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
