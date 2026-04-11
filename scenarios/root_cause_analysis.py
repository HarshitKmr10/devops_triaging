from typing import Optional

from data.service_topology import (
    RCA_ALERTS,
    RCA_LOGS,
    RCA_METRICS,
    SERVICES,
    format_alerts,
    format_dependency_map,
    format_logs,
    format_metrics,
    format_service_info,
)

from .base import ActionResult, BaseScenario, ScenarioConfig

# Ground truth
_ROOT_CAUSE_SERVICE = "order-service"
_ROOT_CAUSE_DB = "inventory-db"
_ROOT_CAUSE_KEYWORDS = frozenset({
    "connection pool", "slow query", "missing index", "inventory",
    "reconciliation", "deployment", "v2.5.1", "exhausted",
})
_REMEDIATION_KEYWORDS = frozenset({
    "kill", "terminate", "index", "add index", "create index",
    "increase pool", "pool size", "rollback", "revert",
})
_RELEVANT_SERVICES = frozenset({"order-service", "api-gateway", "inventory-db"})
_SCENARIO_SERVICES = ("order-service", "api-gateway", "inventory-db")


class RootCauseAnalysisScenario(BaseScenario):

    @property
    def config(self) -> ScenarioConfig:
        return ScenarioConfig(
            task_id="root_cause_analysis",
            task_name="Root Cause Analysis",
            difficulty="medium",
            description=(
                "You are an on-call SRE investigating a service degradation. "
                "The order-service is experiencing high latency and errors. "
                "Your job is to: (1) Investigate the symptoms using alerts, logs, and metrics, "
                "(2) Trace the problem to its root cause, (3) Identify what caused the issue, "
                "and (4) Execute the appropriate remediation. Use all available diagnostic tools "
                "to build a complete picture before declaring the root cause."
            ),
            max_steps=25,
            services=_SCENARIO_SERVICES,
            system_status="DEGRADED - order-service latency critical. API timeouts increasing.",
            noise_services=(),
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
            output = format_alerts(RCA_ALERTS)
            if self._achieve_milestone("viewed_alerts"):
                reward = 0.05
                self._investigation_score += 0.15
                self._mark_investigated()
                feedback = "Alerts reviewed. Note the order-service latency and error alerts."
            else:
                feedback = "Alerts already reviewed."

        elif action_type == "query_logs":
            if service_name and service_name in RCA_LOGS:
                logs = RCA_LOGS[service_name]
                if keyword:
                    logs = tuple(e for e in logs if keyword.lower() in e.message.lower())
                output = format_logs(logs) if logs else "No log entries matching your query."

                if service_name == "order-service" and self._achieve_milestone("logs_order_service"):
                    reward = 0.08
                    self._investigation_score += 0.25
                    self._mark_investigated()
                    feedback = (
                        "Key finding: order-service logs show deployment v2.5.1 followed by "
                        "slow queries and connection pool exhaustion."
                    )
                elif service_name == "inventory-db" and self._achieve_milestone("logs_inventory_db"):
                    reward = 0.08
                    self._investigation_score += 0.25
                    self._mark_investigated()
                    feedback = (
                        "Key finding: inventory-db shows sequential scan on 2.3M rows - "
                        "missing index on 'sku' column."
                    )
                elif service_name in _RELEVANT_SERVICES and self._achieve_milestone(f"logs_{service_name}"):
                    reward = 0.03
                    feedback = f"Logs for {service_name} retrieved."
                else:
                    feedback = f"Logs for {service_name} retrieved."
            else:
                output = f"Service '{service_name}' not found or no logs available."
                feedback = "Try: order-service, api-gateway, or inventory-db"

        elif action_type == "query_metrics":
            if service_name and service_name in RCA_METRICS:
                if metric_type and metric_type in RCA_METRICS[service_name]:
                    from data.service_topology import format_metric
                    output = format_metric(RCA_METRICS[service_name][metric_type])
                else:
                    output = format_metrics(RCA_METRICS[service_name])

                if service_name == "order-service" and self._achieve_milestone("metrics_order_service"):
                    reward = 0.05
                    feedback = "order-service metrics show latency spike and connection pool at 100%."
                elif service_name == "inventory-db" and self._achieve_milestone("metrics_inventory_db"):
                    reward = 0.05
                    feedback = "inventory-db CPU at 88% with 98 active connections - near saturation."
                elif service_name in _RELEVANT_SERVICES and self._achieve_milestone(f"metrics_{service_name}"):
                    reward = 0.03
                    feedback = f"Metrics for {service_name} retrieved."
                else:
                    feedback = f"Metrics for {service_name} retrieved."
            else:
                output = f"No metrics available for '{service_name}'."
                feedback = "Try: order-service, api-gateway, or inventory-db"

        elif action_type == "inspect_service":
            if service_name and service_name in SERVICES:
                output = format_service_info(SERVICES[service_name])
                if self._achieve_milestone(f"inspect_{service_name}"):
                    reward = 0.02
                feedback = f"Service details for {service_name}."
            else:
                output = f"Service '{service_name}' not found."
                feedback = "Check available services."

        elif action_type == "check_dependencies":
            output = format_dependency_map(_SCENARIO_SERVICES)
            if self._achieve_milestone("checked_deps"):
                reward = 0.03
                feedback = "Dependency map shows: api-gateway -> order-service -> inventory-db"
            else:
                feedback = "Dependencies already reviewed."

        elif action_type == "run_diagnostic":
            if service_name == "order-service":
                output = (
                    "Diagnostic: order-service\n"
                    "  DB Connection Pool: 25/25 (EXHAUSTED)\n"
                    "  Active Queries: 18 running > 10s\n"
                    "  Oldest Query: SELECT o.*, i.* FROM orders JOIN inventory... (running 340s)\n"
                    "  Thread Pool: 45/50 blocked on DB acquire\n"
                    "  Last Deployment: v2.5.1 at 14:18:30Z (inventory-reconciliation-job)"
                )
                if self._achieve_milestone("diag_order"):
                    reward = 0.05
                    feedback = "Critical diagnostic: connection pool exhausted with long-running queries."
            elif service_name == "inventory-db":
                output = (
                    "Diagnostic: inventory-db\n"
                    "  Active Connections: 98/100\n"
                    "  Longest Running Query: 340s (SELECT ... JOIN inventory ON sku)\n"
                    "  Table 'inventory': 2.3M rows, NO index on 'sku' column\n"
                    "  Table 'orders': 890K rows\n"
                    "  Sequential Scans (last 10m): 47\n"
                    "  Lock Waits: 12 pending"
                )
                if self._achieve_milestone("diag_inventory_db"):
                    reward = 0.05
                    feedback = "Critical finding: no index on inventory.sku causing sequential scans."
            else:
                output = f"Diagnostic on {service_name}: No anomalies detected."
                feedback = "This service appears healthy. Focus on order-service and inventory-db."

        elif action_type == "classify_severity":
            if severity and severity.upper() == "P1":
                if self._achieve_milestone("classified_p1"):
                    reward = 0.05
                    feedback = "Correct - P1 severity. Order processing is critically impaired."
            elif severity:
                feedback = f"{severity} may be too low given the order processing impact."
            else:
                feedback = "Provide severity: P1-P4"

        elif action_type == "identify_root_cause":
            if root_cause:
                cause_lower = root_cause.lower()
                svc = (service_name or "").lower()

                matches = sum(1 for kw in _ROOT_CAUSE_KEYWORDS if kw in cause_lower)

                if matches >= 3 and (svc in (_ROOT_CAUSE_SERVICE, _ROOT_CAUSE_DB) or any(
                    s in cause_lower for s in (_ROOT_CAUSE_SERVICE, _ROOT_CAUSE_DB)
                )):
                    if self._achieve_milestone("correct_root_cause"):
                        reward = 0.25
                        self._diagnosis_score += 1.0
                        feedback = (
                            "Excellent root cause analysis! The deployment v2.5.1 added an inventory "
                            "reconciliation query with a missing index on inventory.sku, causing "
                            "sequential scans on 2.3M rows that exhausted the connection pool."
                        )
                    else:
                        feedback = "Root cause already identified."
                elif matches >= 1:
                    if self._achieve_milestone("partial_root_cause"):
                        reward = 0.10
                        feedback = (
                            "Partially correct. You're on the right track. Consider: what specific "
                            "change caused the slow queries? What's missing from the database?"
                        )
                else:
                    feedback = "Not quite. Look more carefully at the logs and diagnostics for clues about what changed recently."
            else:
                feedback = "Please provide a root_cause description."

        elif action_type == "execute_remediation":
            if remediation:
                rem_lower = remediation.lower()
                matches = sum(1 for kw in _REMEDIATION_KEYWORDS if kw in rem_lower)
                if matches >= 2:
                    if self._achieve_milestone("correct_remediation"):
                        reward = 0.20
                        self._resolution_score += 1.0
                        feedback = (
                            "Excellent remediation! Killing long-running queries and adding an index "
                            "on inventory.sku will resolve the connection pool exhaustion."
                        )
                        self._done = True
                elif matches >= 1:
                    if self._achieve_milestone("partial_remediation"):
                        reward = 0.08
                        feedback = (
                            "Good start, but consider a more comprehensive fix. "
                            "Both the immediate symptom (stuck queries) and root cause (missing index) "
                            "need to be addressed."
                        )
                else:
                    feedback = "This remediation doesn't address the core issue. Think about what's causing the connection pool to exhaust."
            else:
                feedback = "Please provide a remediation action."

        elif action_type == "escalate":
            if team:
                if self._achieve_milestone("escalated"):
                    reward = 0.03
                feedback = f"Escalated to {team}. Now focus on diagnosis and remediation."

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
