"""
Composable failure type definitions for procedural scenario generation.

Each FailureType knows how to generate realistic alerts, logs, metrics,
and ground truth for a specific class of production incident.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import random

from data.service_topology import (
    Alert, LogEntry, MetricSnapshot, ServiceDefinition, SERVICES,
)


@dataclass(frozen=True)
class GroundTruth:
    """Known-correct answers for grading a generated scenario."""

    root_cause_service: str
    root_cause_description: str
    root_cause_keywords: frozenset[str]
    correct_severity: str
    correct_team: str
    remediation_keywords: frozenset[str]
    cascade_chain: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FailureType:
    """A composable incident failure archetype."""

    name: str
    category: str  # deployment, config, resource, dependency, security, network
    description: str
    severity_range: Tuple[str, ...]  # Possible severities
    log_templates: Tuple[str, ...]
    alert_templates: Tuple[str, ...]
    metric_impacts: Dict[str, Tuple[float, float]]  # metric -> (normal_mult, incident_mult)
    root_cause_keywords: frozenset[str]
    remediation_keywords: frozenset[str]
    remediation_description: str

    def generate_alerts(
        self,
        primary_service: str,
        affected_services: Tuple[str, ...],
        rng: random.Random,
        timestamp_base: str = "2024-03-15T14:",
    ) -> Tuple[Alert, ...]:
        """Generate realistic alerts for this failure type."""
        alerts: list[Alert] = []
        minute = 20

        # Primary service gets critical alerts
        for i, template in enumerate(self.alert_templates[:3]):
            alerts.append(Alert(
                alert_id=f"ALT-G{rng.randint(1000, 9999)}",
                severity="CRITICAL" if i == 0 else "WARNING",
                service=primary_service,
                title=template.format(service=primary_service),
                description=f"Automated alert: {template.format(service=primary_service)}. "
                            f"Impact on {primary_service} detected.",
                timestamp=f"{timestamp_base}{minute:02d}:00Z",
            ))
            minute += rng.randint(1, 3)

        # Affected services get warning/info alerts
        for svc in affected_services:
            if svc == primary_service:
                continue
            alerts.append(Alert(
                alert_id=f"ALT-G{rng.randint(1000, 9999)}",
                severity="WARNING",
                service=svc,
                title=f"Degraded performance on {svc}",
                description=f"{svc} experiencing elevated errors. Possible upstream dependency issue.",
                timestamp=f"{timestamp_base}{minute:02d}:00Z",
            ))
            minute += rng.randint(1, 2)

        # Add a noise alert
        noise_services = [s for s in SERVICES if s not in affected_services and s != primary_service]
        if noise_services:
            noise_svc = rng.choice(noise_services)
            alerts.append(Alert(
                alert_id=f"ALT-G{rng.randint(1000, 9999)}",
                severity="INFO",
                service=noise_svc,
                title=f"Routine maintenance alert on {noise_svc}",
                description=f"Scheduled health check warning. Non-critical.",
                timestamp=f"{timestamp_base}{minute:02d}:00Z",
            ))

        return tuple(alerts)

    def generate_logs(
        self,
        primary_service: str,
        affected_services: Tuple[str, ...],
        rng: random.Random,
        timestamp_base: str = "2024-03-15T14:",
    ) -> Dict[str, Tuple[LogEntry, ...]]:
        """Generate realistic log entries for this failure type."""
        logs: Dict[str, list[LogEntry]] = {}
        minute = 18

        # Primary service: detailed failure logs
        primary_logs: list[LogEntry] = []
        template_vars = {
            "service": primary_service,
            "config_name": f"{primary_service}-config-v2",
            "ver": f"{rng.randint(2,5)}.{rng.randint(0,9)}.{rng.randint(0,9)}",
            "feature": f"feature-{rng.randint(100,999)}",
            "dependency": primary_service,
            "error_detail": "validation mismatch in new config",
            "expiry_date": "2024-03-14",
            "source": "upstream-client",
        }
        for template in self.log_templates:
            level = "ERROR" if "error" in template.lower() or "fail" in template.lower() else "WARN"
            try:
                message = template.format(**template_vars)
            except KeyError:
                message = template
            primary_logs.append(LogEntry(
                timestamp=f"{timestamp_base}{minute:02d}:{rng.randint(0, 59):02d}Z",
                level=level,
                service=primary_service,
                message=message,
            ))
            minute += rng.randint(0, 2)
        logs[primary_service] = primary_logs

        # Affected services: upstream failure logs
        for svc in affected_services:
            if svc == primary_service:
                continue
            svc_logs = [
                LogEntry(
                    timestamp=f"{timestamp_base}{minute:02d}:00Z",
                    level="ERROR",
                    service=svc,
                    message=f"Upstream dependency {primary_service} returning errors",
                ),
                LogEntry(
                    timestamp=f"{timestamp_base}{minute + 1:02d}:00Z",
                    level="WARN",
                    service=svc,
                    message=f"Elevated error rate due to {primary_service} degradation",
                ),
            ]
            logs[svc] = svc_logs
            minute += 2

        return {k: tuple(v) for k, v in logs.items()}

    def generate_metrics(
        self,
        primary_service: str,
        affected_services: Tuple[str, ...],
        rng: random.Random,
    ) -> Dict[str, Dict[str, MetricSnapshot]]:
        """Generate metric snapshots showing the failure impact."""
        metrics: Dict[str, Dict[str, MetricSnapshot]] = {}

        svc_def = SERVICES.get(primary_service)
        if not svc_def:
            return metrics

        # Primary service: impacted metrics
        primary_metrics: Dict[str, MetricSnapshot] = {}
        for metric_name, (normal_mult, incident_mult) in self.metric_impacts.items():
            base_values = {
                "error_rate": svc_def.normal_error_rate * 100,
                "latency": float(svc_def.normal_latency_ms),
                "cpu": svc_def.normal_cpu_pct,
                "memory": svc_def.normal_memory_pct,
                "connections": 40.0,
            }
            base = base_values.get(metric_name, 50.0)
            units = {
                "error_rate": "%", "latency": "ms", "cpu": "%",
                "memory": "%", "connections": "%",
            }
            normal_val = base * normal_mult
            incident_val = base * incident_mult * rng.uniform(0.8, 1.2)

            primary_metrics[metric_name] = MetricSnapshot(
                service=primary_service,
                metric_type=metric_name,
                current_value=round(incident_val, 1),
                normal_value=round(normal_val, 1),
                unit=units.get(metric_name, ""),
                timestamp="2024-03-15T14:25:00Z",
                trend="spike" if incident_mult > 5 else "rising",
            )
        metrics[primary_service] = primary_metrics

        # Affected services: mild metric degradation
        for svc in affected_services:
            if svc == primary_service:
                continue
            svc_def_aff = SERVICES.get(svc)
            if not svc_def_aff:
                continue
            metrics[svc] = {
                "error_rate": MetricSnapshot(
                    svc, "error_rate",
                    round(svc_def_aff.normal_error_rate * 100 * rng.uniform(10, 30), 1),
                    round(svc_def_aff.normal_error_rate * 100, 2),
                    "%", "2024-03-15T14:25:00Z", "rising",
                ),
                "latency": MetricSnapshot(
                    svc, "latency",
                    round(svc_def_aff.normal_latency_ms * rng.uniform(3, 8), 1),
                    float(svc_def_aff.normal_latency_ms),
                    "ms", "2024-03-15T14:25:00Z", "rising",
                ),
            }

        return metrics

    def get_ground_truth(
        self, primary_service: str, cascade_chain: Tuple[str, ...] = ()
    ) -> GroundTruth:
        """Generate the ground truth for grading."""
        svc_def = SERVICES.get(primary_service)
        team = svc_def.team if svc_def else "platform-team"
        return GroundTruth(
            root_cause_service=primary_service,
            root_cause_description=f"{self.name} on {primary_service}: {self.description}",
            root_cause_keywords=self.root_cause_keywords | frozenset({primary_service}),
            correct_severity="P1" if len(cascade_chain) > 2 else "P2",
            correct_team=team,
            remediation_keywords=self.remediation_keywords,
            cascade_chain=cascade_chain,
        )


# ─── Failure Type Registry ───────────────────────────────────────────────

DEPLOYMENT_BUG = FailureType(
    name="deployment_bug",
    category="deployment",
    description="A recent deployment introduced a code bug causing service failures",
    severity_range=("P1", "P2"),
    log_templates=(
        "Deployment v{ver} started - feature: {feature}",
        "Deployment v{ver} completed successfully",
        "NullPointerException in {service}.processRequest(): field is null",
        "Error rate exceeded threshold after deployment v{ver}",
        "Health check failed: internal error after v{ver} rollout",
    ),
    alert_templates=(
        "Error rate critical on {service}",
        "Health check failures on {service}",
        "Deployment anomaly detected on {service}",
    ),
    metric_impacts={
        "error_rate": (1.0, 50.0),
        "latency": (1.0, 15.0),
        "cpu": (1.0, 2.5),
    },
    root_cause_keywords=frozenset({"deployment", "deploy", "release", "bug", "rollout", "version"}),
    remediation_keywords=frozenset({"rollback", "revert", "previous version", "undo deploy"}),
    remediation_description="Rollback to the previous deployment version",
)

CONFIG_CHANGE = FailureType(
    name="config_change",
    category="config",
    description="A configuration change broke service functionality",
    severity_range=("P1", "P2"),
    log_templates=(
        "Config deployment initiated: {config_name}",
        "Loading new configuration: {config_name}",
        "Config deployment completed: {config_name}",
        "ERROR: Validation failed with new config - {error_detail}",
        "Service rejecting requests due to config mismatch",
    ),
    alert_templates=(
        "Configuration error on {service}",
        "Request rejection rate spiking on {service}",
        "Service degradation after config change on {service}",
    ),
    metric_impacts={
        "error_rate": (1.0, 80.0),
        "latency": (1.0, 1.5),
        "cpu": (1.0, 1.1),
    },
    root_cause_keywords=frozenset({"config", "configuration", "setting", "change", "update", "mismatch"}),
    remediation_keywords=frozenset({"rollback config", "revert config", "restore", "previous config"}),
    remediation_description="Rollback the configuration to the previous version",
)

RESOURCE_EXHAUSTION = FailureType(
    name="resource_exhaustion",
    category="resource",
    description="A resource (connections, memory, disk) was exhausted",
    severity_range=("P1", "P2"),
    log_templates=(
        "Resource pool utilization at 80%",
        "Resource pool utilization at 95% - WARNING",
        "Resource pool EXHAUSTED: all resources in use",
        "Timeout waiting for available resource (30s exceeded)",
        "Rejecting new requests: no resources available",
    ),
    alert_templates=(
        "Resource exhaustion on {service}",
        "Connection/memory limit reached on {service}",
        "Service rejecting requests on {service}",
    ),
    metric_impacts={
        "connections": (1.0, 2.5),
        "latency": (1.0, 30.0),
        "error_rate": (1.0, 20.0),
        "cpu": (1.0, 3.0),
        "memory": (1.0, 2.2),
    },
    root_cause_keywords=frozenset({
        "exhaustion", "exhausted", "pool", "connection", "memory",
        "disk", "limit", "full", "saturated",
    }),
    remediation_keywords=frozenset({
        "increase pool", "kill", "terminate", "restart", "scale",
        "add capacity", "clear cache", "free",
    }),
    remediation_description="Increase resource limits and terminate stuck consumers",
)

DEPENDENCY_FAILURE = FailureType(
    name="dependency_failure",
    category="dependency",
    description="An external dependency became unavailable",
    severity_range=("P1", "P2", "P3"),
    log_templates=(
        "Connection to {dependency} failed: connection refused",
        "Retry attempt 1/3 to {dependency} failed",
        "Circuit breaker OPEN for {dependency}",
        "All retries exhausted for {dependency}",
        "Falling back to degraded mode without {dependency}",
    ),
    alert_templates=(
        "Dependency {service} unreachable",
        "Circuit breaker open on {service}",
        "Upstream failures from {service}",
    ),
    metric_impacts={
        "error_rate": (1.0, 40.0),
        "latency": (1.0, 20.0),
    },
    root_cause_keywords=frozenset({
        "dependency", "upstream", "downstream", "connection refused",
        "unreachable", "circuit breaker", "timeout",
    }),
    remediation_keywords=frozenset({
        "restart", "reconnect", "failover", "switch", "backup",
        "restore dependency", "health check",
    }),
    remediation_description="Restore the failed dependency or switch to failover",
)

CERT_EXPIRY = FailureType(
    name="cert_expiry",
    category="security",
    description="A TLS certificate expired causing connection failures",
    severity_range=("P1", "P2"),
    log_templates=(
        "TLS handshake failed: certificate expired",
        "SSL ERROR: certificate has expired (not after: {expiry_date})",
        "HTTPS connection rejected: invalid certificate",
        "All downstream HTTPS calls failing with SSL error",
        "Certificate renewal required for {service}",
    ),
    alert_templates=(
        "TLS certificate expired on {service}",
        "SSL handshake failures on {service}",
        "HTTPS connectivity broken on {service}",
    ),
    metric_impacts={
        "error_rate": (1.0, 95.0),
        "latency": (1.0, 1.0),
        "cpu": (1.0, 0.8),
    },
    root_cause_keywords=frozenset({
        "certificate", "cert", "tls", "ssl", "expired", "expiry",
        "https", "handshake",
    }),
    remediation_keywords=frozenset({
        "renew", "certificate", "cert", "rotate", "replace",
        "install cert", "update cert",
    }),
    remediation_description="Renew or replace the expired TLS certificate",
)

MEMORY_LEAK = FailureType(
    name="memory_leak",
    category="resource",
    description="A memory leak caused gradual performance degradation and OOM",
    severity_range=("P2", "P3"),
    log_templates=(
        "GC pause time increasing: 500ms (normal: 20ms)",
        "Heap usage at 85% - approaching limit",
        "WARNING: Memory allocation failures detected",
        "OutOfMemoryError: Java heap space",
        "Service restarted by OOM killer (exit code 137)",
    ),
    alert_templates=(
        "Memory usage critical on {service}",
        "OOM restarts detected on {service}",
        "GC pressure elevated on {service}",
    ),
    metric_impacts={
        "memory": (1.0, 2.4),
        "cpu": (1.0, 2.0),
        "latency": (1.0, 10.0),
        "error_rate": (1.0, 15.0),
    },
    root_cause_keywords=frozenset({
        "memory", "leak", "oom", "heap", "gc", "garbage collection",
        "out of memory", "allocation",
    }),
    remediation_keywords=frozenset({
        "restart", "increase memory", "heap size", "fix leak",
        "patch", "scale", "memory limit",
    }),
    remediation_description="Restart affected instances and increase memory limits",
)

DNS_MISCONFIGURATION = FailureType(
    name="dns_misconfiguration",
    category="network",
    description="A DNS change caused service discovery failures",
    severity_range=("P1", "P2"),
    log_templates=(
        "DNS resolution failed for {service}.internal: NXDOMAIN",
        "Service discovery: cannot resolve {service} endpoint",
        "Connection failed: DNS lookup timed out for {service}",
        "Fallback to cached DNS entry (stale: 2h old)",
        "Multiple services reporting DNS resolution failures",
    ),
    alert_templates=(
        "DNS resolution failures for {service}",
        "Service discovery broken on {service}",
        "Network connectivity issues on {service}",
    ),
    metric_impacts={
        "error_rate": (1.0, 70.0),
        "latency": (1.0, 50.0),
    },
    root_cause_keywords=frozenset({
        "dns", "resolution", "nxdomain", "service discovery",
        "domain", "lookup", "nameserver",
    }),
    remediation_keywords=frozenset({
        "dns", "revert dns", "fix record", "restore", "flush cache",
        "update record", "rollback dns",
    }),
    remediation_description="Revert the DNS change and flush DNS caches",
)

RATE_LIMIT_BREACH = FailureType(
    name="rate_limit_breach",
    category="network",
    description="A traffic spike or retry storm breached rate limits",
    severity_range=("P2", "P3"),
    log_templates=(
        "Rate limit exceeded: 429 Too Many Requests",
        "Incoming request rate: 15,000 rps (limit: 5,000 rps)",
        "Rate limiter dropping requests from {source}",
        "Retry storm detected: clients retrying failed requests exponentially",
        "Backend overwhelmed by retry traffic",
    ),
    alert_templates=(
        "Rate limit breach on {service}",
        "Traffic spike detected on {service}",
        "429 response rate elevated on {service}",
    ),
    metric_impacts={
        "error_rate": (1.0, 30.0),
        "latency": (1.0, 5.0),
        "cpu": (1.0, 2.8),
    },
    root_cause_keywords=frozenset({
        "rate limit", "429", "throttle", "traffic", "spike",
        "retry storm", "overwhelmed", "rps",
    }),
    remediation_keywords=frozenset({
        "increase limit", "rate limit", "throttle", "block",
        "circuit breaker", "backoff", "shed load",
    }),
    remediation_description="Increase rate limits and enable circuit breakers to stop retry storms",
)


FAILURE_REGISTRY: Dict[str, FailureType] = {
    "deployment_bug": DEPLOYMENT_BUG,
    "config_change": CONFIG_CHANGE,
    "resource_exhaustion": RESOURCE_EXHAUSTION,
    "dependency_failure": DEPENDENCY_FAILURE,
    "cert_expiry": CERT_EXPIRY,
    "memory_leak": MEMORY_LEAK,
    "dns_misconfiguration": DNS_MISCONFIGURATION,
    "rate_limit_breach": RATE_LIMIT_BREACH,
}
