"""
Service topology and mock data generators for incident scenarios.

Defines the microservice architecture, alert templates, log generators,
and metric simulators used across all incident response scenarios.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ServiceDefinition:
    """Immutable definition of a microservice in the topology."""

    name: str
    team: str
    description: str
    port: int
    dependencies: tuple[str, ...] = ()
    health_endpoint: str = "/health"
    normal_latency_ms: int = 50
    normal_error_rate: float = 0.001
    normal_cpu_pct: float = 25.0
    normal_memory_pct: float = 40.0


# ─── Service Definitions ────────────────────────────────────────────────

SERVICES: Dict[str, ServiceDefinition] = {
    "auth-service": ServiceDefinition(
        name="auth-service",
        team="platform-team",
        description="JWT token validation and user authentication",
        port=8001,
        dependencies=("redis-cache",),
        normal_latency_ms=15,
        normal_cpu_pct=20.0,
    ),
    "api-gateway": ServiceDefinition(
        name="api-gateway",
        team="platform-team",
        description="Main API gateway, routes requests to backend services",
        port=8080,
        dependencies=("auth-service", "user-service", "order-service", "payment-service"),
        normal_latency_ms=30,
        normal_cpu_pct=35.0,
    ),
    "user-service": ServiceDefinition(
        name="user-service",
        team="identity-team",
        description="User profile management and lookup",
        port=8002,
        dependencies=("auth-service", "postgres-users"),
        normal_latency_ms=45,
    ),
    "order-service": ServiceDefinition(
        name="order-service",
        team="commerce-team",
        description="Order creation, tracking, and inventory management",
        port=8003,
        dependencies=("user-service", "payment-service", "inventory-db"),
        normal_latency_ms=80,
    ),
    "payment-service": ServiceDefinition(
        name="payment-service",
        team="payments-team",
        description="Payment processing and transaction management",
        port=8004,
        dependencies=("auth-service", "postgres-payments", "stripe-gateway"),
        normal_latency_ms=120,
    ),
    "notification-service": ServiceDefinition(
        name="notification-service",
        team="comms-team",
        description="Email, SMS, and push notification dispatch",
        port=8005,
        dependencies=("user-service", "rabbitmq"),
        normal_latency_ms=200,
    ),
    "inventory-db": ServiceDefinition(
        name="inventory-db",
        team="commerce-team",
        description="PostgreSQL database for inventory and order data",
        port=5432,
        normal_latency_ms=5,
        normal_cpu_pct=30.0,
    ),
    "postgres-users": ServiceDefinition(
        name="postgres-users",
        team="identity-team",
        description="PostgreSQL database for user data",
        port=5433,
        normal_latency_ms=5,
    ),
    "postgres-payments": ServiceDefinition(
        name="postgres-payments",
        team="payments-team",
        description="PostgreSQL database for payment records",
        port=5434,
        normal_latency_ms=5,
    ),
    "redis-cache": ServiceDefinition(
        name="redis-cache",
        team="platform-team",
        description="Redis cache for session tokens and rate limiting",
        port=6379,
        normal_latency_ms=2,
        normal_cpu_pct=10.0,
    ),
    "rabbitmq": ServiceDefinition(
        name="rabbitmq",
        team="platform-team",
        description="Message broker for async communication",
        port=5672,
        normal_latency_ms=3,
    ),
    "stripe-gateway": ServiceDefinition(
        name="stripe-gateway",
        team="payments-team",
        description="External payment processor integration (Stripe)",
        port=443,
        normal_latency_ms=300,
    ),
}


@dataclass(frozen=True)
class Alert:
    """Immutable alert from the monitoring system."""

    alert_id: str
    severity: str  # CRITICAL, WARNING, INFO
    service: str
    title: str
    description: str
    timestamp: str
    status: str = "firing"  # firing, resolved


@dataclass(frozen=True)
class LogEntry:
    """Immutable log entry from a service."""

    timestamp: str
    level: str  # ERROR, WARN, INFO, DEBUG
    service: str
    message: str
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class MetricSnapshot:
    """Immutable metric data point."""

    service: str
    metric_type: str
    current_value: float
    normal_value: float
    unit: str
    timestamp: str
    trend: str = "stable"  # rising, falling, stable, spike


# ─── Alert Triage Scenario Data ─────────────────────────────────────────

ALERT_TRIAGE_ALERTS: tuple[Alert, ...] = (
    Alert(
        alert_id="ALT-001",
        severity="CRITICAL",
        service="payment-service",
        title="HTTP 500 Error Rate Exceeded",
        description="500 error rate at 45% of requests (threshold: 5%). Customers reporting failed checkouts.",
        timestamp="2024-03-15T14:25:00Z",
    ),
    Alert(
        alert_id="ALT-002",
        severity="CRITICAL",
        service="payment-service",
        title="Health Check Failures",
        description="Health check failing on 3 of 5 instances. Auto-scaling triggered but new instances also failing.",
        timestamp="2024-03-15T14:26:00Z",
    ),
    Alert(
        alert_id="ALT-003",
        severity="CRITICAL",
        service="payment-service",
        title="Transaction Failure Rate Critical",
        description="Transaction failure rate at 38% (threshold: 2%). Revenue impact estimated at $45K/hour.",
        timestamp="2024-03-15T14:27:00Z",
    ),
    Alert(
        alert_id="ALT-004",
        severity="WARNING",
        service="api-gateway",
        title="Upstream Timeout Rate Increasing",
        description="Timeout rate to payment-service at 30% (threshold: 5%). Circuit breaker may trip.",
        timestamp="2024-03-15T14:26:30Z",
    ),
    Alert(
        alert_id="ALT-005",
        severity="WARNING",
        service="api-gateway",
        title="Response Latency P99 Elevated",
        description="P99 latency at 2400ms (threshold: 1000ms). Degraded user experience on checkout flows.",
        timestamp="2024-03-15T14:27:00Z",
    ),
    Alert(
        alert_id="ALT-006",
        severity="WARNING",
        service="user-service",
        title="Database Connection Count Elevated",
        description="Connection pool utilization at 85% (threshold: 75%). May affect user lookups.",
        timestamp="2024-03-15T14:28:00Z",
    ),
    Alert(
        alert_id="ALT-007",
        severity="INFO",
        service="notification-service",
        title="Queue Depth Increasing",
        description="RabbitMQ queue depth at 1,500 messages (normal: ~200). Notification delays expected.",
        timestamp="2024-03-15T14:28:30Z",
    ),
    Alert(
        alert_id="ALT-008",
        severity="INFO",
        service="monitoring",
        title="Disk Usage Warning",
        description="Log aggregator disk usage at 78% (threshold: 80%). Non-urgent cleanup recommended.",
        timestamp="2024-03-15T14:20:00Z",
    ),
)

ALERT_TRIAGE_LOGS: Dict[str, tuple[LogEntry, ...]] = {
    "payment-service": (
        LogEntry("2024-03-15T14:20:00Z", "INFO", "payment-service", "Deployment v3.2.1 started - release: checkout-redesign"),
        LogEntry("2024-03-15T14:20:45Z", "INFO", "payment-service", "Deployment v3.2.1 completed. Rolling restart in progress."),
        LogEntry("2024-03-15T14:22:00Z", "ERROR", "payment-service", "NullPointerException in PaymentProcessor.processCharge(): card_token is null", "trace-8a2f"),
        LogEntry("2024-03-15T14:22:01Z", "ERROR", "payment-service", "Failed to process payment: missing required field 'card_token' after v3.2.1 migration", "trace-8a2f"),
        LogEntry("2024-03-15T14:23:00Z", "ERROR", "payment-service", "Stripe API call failed: invalid request - card_token format changed in v3.2.1", "trace-9b3c"),
        LogEntry("2024-03-15T14:24:00Z", "WARN", "payment-service", "Error rate exceeded 30% threshold. Circuit breaker OPEN for Stripe calls."),
        LogEntry("2024-03-15T14:25:00Z", "ERROR", "payment-service", "Health check failed: dependency stripe-gateway unreachable (circuit breaker open)"),
    ),
    "api-gateway": (
        LogEntry("2024-03-15T14:24:00Z", "WARN", "api-gateway", "Upstream payment-service returning 500 errors at elevated rate"),
        LogEntry("2024-03-15T14:25:00Z", "WARN", "api-gateway", "Circuit breaker for payment-service at HALF-OPEN state"),
        LogEntry("2024-03-15T14:26:00Z", "ERROR", "api-gateway", "Timeout waiting for payment-service response (30s exceeded)"),
    ),
    "user-service": (
        LogEntry("2024-03-15T14:26:00Z", "WARN", "user-service", "Elevated query times on user lookup - possibly related to increased retry traffic"),
        LogEntry("2024-03-15T14:27:00Z", "INFO", "user-service", "Connection pool utilization rising due to retry storms from downstream failures"),
    ),
    "notification-service": (
        LogEntry("2024-03-15T14:27:00Z", "INFO", "notification-service", "Queue depth increasing - payment failure notifications backing up"),
        LogEntry("2024-03-15T14:28:00Z", "WARN", "notification-service", "Processing delay: 45s average (normal: 2s)"),
    ),
}

ALERT_TRIAGE_METRICS: Dict[str, Dict[str, MetricSnapshot]] = {
    "payment-service": {
        "error_rate": MetricSnapshot("payment-service", "error_rate", 45.0, 0.1, "%", "2024-03-15T14:27:00Z", "spike"),
        "latency": MetricSnapshot("payment-service", "latency_p99", 8500.0, 120.0, "ms", "2024-03-15T14:27:00Z", "spike"),
        "cpu": MetricSnapshot("payment-service", "cpu", 78.0, 25.0, "%", "2024-03-15T14:27:00Z", "rising"),
        "memory": MetricSnapshot("payment-service", "memory", 72.0, 40.0, "%", "2024-03-15T14:27:00Z", "rising"),
    },
    "api-gateway": {
        "error_rate": MetricSnapshot("api-gateway", "error_rate", 22.0, 0.5, "%", "2024-03-15T14:27:00Z", "rising"),
        "latency": MetricSnapshot("api-gateway", "latency_p99", 2400.0, 30.0, "ms", "2024-03-15T14:27:00Z", "spike"),
        "cpu": MetricSnapshot("api-gateway", "cpu", 55.0, 35.0, "%", "2024-03-15T14:27:00Z", "rising"),
    },
    "user-service": {
        "error_rate": MetricSnapshot("user-service", "error_rate", 2.5, 0.1, "%", "2024-03-15T14:27:00Z", "rising"),
        "latency": MetricSnapshot("user-service", "latency_p99", 350.0, 45.0, "ms", "2024-03-15T14:27:00Z", "rising"),
        "connections": MetricSnapshot("user-service", "db_connections", 85.0, 40.0, "%", "2024-03-15T14:27:00Z", "rising"),
    },
    "notification-service": {
        "error_rate": MetricSnapshot("notification-service", "error_rate", 0.5, 0.1, "%", "2024-03-15T14:27:00Z", "stable"),
        "latency": MetricSnapshot("notification-service", "latency_p99", 450.0, 200.0, "ms", "2024-03-15T14:27:00Z", "rising"),
    },
}


# ─── Root Cause Analysis Scenario Data ───────────────────────────────────

RCA_ALERTS: tuple[Alert, ...] = (
    Alert(
        alert_id="ALT-101",
        severity="CRITICAL",
        service="order-service",
        title="Latency P99 Critical",
        description="P99 latency at 5200ms (threshold: 500ms). Order processing severely degraded.",
        timestamp="2024-03-15T14:23:00Z",
    ),
    Alert(
        alert_id="ALT-102",
        severity="WARNING",
        service="api-gateway",
        title="Upstream Timeouts from order-service",
        description="Timeout rate to order-service at 25%. Users seeing 504 Gateway Timeout errors.",
        timestamp="2024-03-15T14:24:00Z",
    ),
    Alert(
        alert_id="ALT-103",
        severity="WARNING",
        service="order-service",
        title="Error Rate Elevated",
        description="Error rate at 15% (threshold: 1%). Database connection errors in stack traces.",
        timestamp="2024-03-15T14:24:30Z",
    ),
    Alert(
        alert_id="ALT-104",
        severity="INFO",
        service="inventory-db",
        title="Active Connections Near Limit",
        description="Active connections: 95/100. Connection pool saturation imminent.",
        timestamp="2024-03-15T14:25:00Z",
    ),
)

RCA_LOGS: Dict[str, tuple[LogEntry, ...]] = {
    "order-service": (
        LogEntry("2024-03-15T14:18:00Z", "INFO", "order-service", "Deployment v2.5.1 started - feature: inventory-reconciliation-job"),
        LogEntry("2024-03-15T14:18:30Z", "INFO", "order-service", "Deployment v2.5.1 completed successfully. New cron job registered."),
        LogEntry("2024-03-15T14:19:00Z", "INFO", "order-service", "Inventory reconciliation job started - querying all orders with inventory JOIN"),
        LogEntry("2024-03-15T14:20:00Z", "WARN", "order-service", "Slow query detected: SELECT o.*, i.* FROM orders o JOIN inventory i ON o.sku = i.sku WHERE o.status = 'pending' -- execution time: 12.5s (missing index on inventory.sku)"),
        LogEntry("2024-03-15T14:21:00Z", "WARN", "order-service", "DB connection pool utilization at 80% (20 active / 25 max)"),
        LogEntry("2024-03-15T14:21:30Z", "WARN", "order-service", "DB connection pool utilization at 95% (24 active / 25 max)"),
        LogEntry("2024-03-15T14:22:00Z", "ERROR", "order-service", "Connection pool exhausted: all 25 connections in use. Timeout waiting for available connection (30s)", "trace-pool-001"),
        LogEntry("2024-03-15T14:22:30Z", "ERROR", "order-service", "Failed to process order ORD-78234: unable to acquire DB connection within timeout", "trace-pool-002"),
        LogEntry("2024-03-15T14:23:00Z", "ERROR", "order-service", "Connection pool exhausted. Rejecting new requests. 15 queries running > 10s each.", "trace-pool-003"),
        LogEntry("2024-03-15T14:24:00Z", "ERROR", "order-service", "Health check degraded: DB connectivity impaired. Active long-running queries: 18"),
    ),
    "api-gateway": (
        LogEntry("2024-03-15T14:23:00Z", "WARN", "api-gateway", "order-service response time exceeding timeout threshold"),
        LogEntry("2024-03-15T14:24:00Z", "ERROR", "api-gateway", "504 Gateway Timeout for /api/orders endpoints. Upstream order-service not responding."),
    ),
    "inventory-db": (
        LogEntry("2024-03-15T14:19:30Z", "WARN", "inventory-db", "Long-running query detected: SELECT o.*, i.* FROM orders JOIN inventory... (pid: 4521, duration: 10s)"),
        LogEntry("2024-03-15T14:20:30Z", "WARN", "inventory-db", "Sequential scan on inventory table (2.3M rows) - no index on column 'sku'"),
        LogEntry("2024-03-15T14:22:00Z", "WARN", "inventory-db", "Active connections: 92/100. Warning threshold reached."),
        LogEntry("2024-03-15T14:23:00Z", "ERROR", "inventory-db", "Connection limit approaching: 98/100 active connections"),
    ),
}

RCA_METRICS: Dict[str, Dict[str, MetricSnapshot]] = {
    "order-service": {
        "latency": MetricSnapshot("order-service", "latency_p99", 5200.0, 80.0, "ms", "2024-03-15T14:24:00Z", "spike"),
        "error_rate": MetricSnapshot("order-service", "error_rate", 15.0, 0.1, "%", "2024-03-15T14:24:00Z", "spike"),
        "cpu": MetricSnapshot("order-service", "cpu", 65.0, 30.0, "%", "2024-03-15T14:24:00Z", "rising"),
        "connections": MetricSnapshot("order-service", "db_connections", 100.0, 40.0, "%", "2024-03-15T14:24:00Z", "spike"),
    },
    "api-gateway": {
        "latency": MetricSnapshot("api-gateway", "latency_p99", 3500.0, 30.0, "ms", "2024-03-15T14:24:00Z", "spike"),
        "error_rate": MetricSnapshot("api-gateway", "error_rate", 18.0, 0.5, "%", "2024-03-15T14:24:00Z", "rising"),
    },
    "inventory-db": {
        "cpu": MetricSnapshot("inventory-db", "cpu", 88.0, 30.0, "%", "2024-03-15T14:24:00Z", "spike"),
        "connections": MetricSnapshot("inventory-db", "active_connections", 98.0, 25.0, "count", "2024-03-15T14:24:00Z", "spike"),
        "latency": MetricSnapshot("inventory-db", "query_latency_p99", 12500.0, 5.0, "ms", "2024-03-15T14:24:00Z", "spike"),
    },
}


# ─── Cascading Failure Scenario Data ─────────────────────────────────────

CASCADE_ALERTS: tuple[Alert, ...] = (
    Alert(
        alert_id="ALT-201",
        severity="CRITICAL",
        service="payment-service",
        title="Transaction Failures Critical",
        description="Transaction failure rate at 52%. All payment processing halted.",
        timestamp="2024-03-15T14:12:00Z",
    ),
    Alert(
        alert_id="ALT-202",
        severity="CRITICAL",
        service="order-service",
        title="Order Creation Failures",
        description="Order creation failure rate at 48%. Cannot verify user identity for new orders.",
        timestamp="2024-03-15T14:11:00Z",
    ),
    Alert(
        alert_id="ALT-203",
        severity="WARNING",
        service="user-service",
        title="Authentication Failures Spiking",
        description="Auth failure rate at 90%. Unable to validate user tokens via auth-service.",
        timestamp="2024-03-15T14:09:00Z",
    ),
    Alert(
        alert_id="ALT-204",
        severity="WARNING",
        service="api-gateway",
        title="401 Response Rate Critical",
        description="401 Unauthorized response rate at 65%. Most authenticated endpoints failing.",
        timestamp="2024-03-15T14:07:00Z",
    ),
    Alert(
        alert_id="ALT-205",
        severity="INFO",
        service="auth-service",
        title="Configuration Updated",
        description="Config deployment jwt-validation-v3 completed at 14:00:15Z.",
        timestamp="2024-03-15T14:00:15Z",
    ),
    Alert(
        alert_id="ALT-206",
        severity="WARNING",
        service="notification-service",
        title="Failed Notification Deliveries",
        description="Cannot send order confirmation emails - user-service lookup failing.",
        timestamp="2024-03-15T14:13:00Z",
    ),
)

CASCADE_LOGS: Dict[str, tuple[LogEntry, ...]] = {
    "auth-service": (
        LogEntry("2024-03-15T13:59:00Z", "INFO", "auth-service", "Config deployment initiated: jwt-validation-v3 (requested by deploy-bot)"),
        LogEntry("2024-03-15T14:00:00Z", "INFO", "auth-service", "Loading new JWT validation config: jwt-validation-v3"),
        LogEntry("2024-03-15T14:00:15Z", "INFO", "auth-service", "Config deployment completed: jwt-validation-v3. New key_id format applied."),
        LogEntry("2024-03-15T14:01:00Z", "WARN", "auth-service", "JWT validation using new config. Key lookup format changed from 'rsa-prod-2024' to 'rsa_prod_2024'"),
        LogEntry("2024-03-15T14:02:00Z", "ERROR", "auth-service", "JWT validation failed: key_id 'rsa-prod-2024' not found in keystore. New config expects 'rsa_prod_2024' (underscore format)"),
        LogEntry("2024-03-15T14:02:01Z", "ERROR", "auth-service", "Token rejection: 95% of tokens use old key_id format 'rsa-prod-2024'"),
        LogEntry("2024-03-15T14:02:30Z", "ERROR", "auth-service", "ALERT: Token rejection rate 95%. All tokens signed with 'rsa-prod-2024' are being rejected by jwt-validation-v3 config"),
        LogEntry("2024-03-15T14:03:00Z", "ERROR", "auth-service", "Downstream services reporting auth failures. Config jwt-validation-v3 may have breaking change in key_id format."),
    ),
    "api-gateway": (
        LogEntry("2024-03-15T14:03:00Z", "WARN", "api-gateway", "auth-service returning 401 for previously valid tokens"),
        LogEntry("2024-03-15T14:05:00Z", "ERROR", "api-gateway", "401 rate spiking: 60% of authenticated requests rejected by auth-service"),
        LogEntry("2024-03-15T14:07:00Z", "ERROR", "api-gateway", "Circuit breaker for auth-service at HALF-OPEN. 65% of requests getting 401."),
    ),
    "user-service": (
        LogEntry("2024-03-15T14:06:00Z", "ERROR", "user-service", "Cannot authenticate incoming requests: auth-service rejecting valid tokens"),
        LogEntry("2024-03-15T14:08:00Z", "ERROR", "user-service", "User lookup failing: 90% of requests fail auth validation"),
        LogEntry("2024-03-15T14:09:00Z", "WARN", "user-service", "Retry storms detected - clients retrying failed auth requests"),
    ),
    "order-service": (
        LogEntry("2024-03-15T14:09:00Z", "ERROR", "order-service", "Cannot create orders: user-service returning auth errors"),
        LogEntry("2024-03-15T14:10:00Z", "ERROR", "order-service", "Order creation failure rate: 48%. User identity verification unavailable."),
        LogEntry("2024-03-15T14:11:00Z", "WARN", "order-service", "Falling back to cached user data for existing orders. New orders blocked."),
    ),
    "payment-service": (
        LogEntry("2024-03-15T14:10:00Z", "ERROR", "payment-service", "Payment processing failing: cannot verify user identity via order-service"),
        LogEntry("2024-03-15T14:11:00Z", "ERROR", "payment-service", "Transaction failures: 52%. Upstream order-service cannot validate orders."),
        LogEntry("2024-03-15T14:12:00Z", "WARN", "payment-service", "Revenue impact: ~$120K/hour. All new transactions halted."),
    ),
    "notification-service": (
        LogEntry("2024-03-15T14:12:00Z", "WARN", "notification-service", "Cannot fetch user data for notifications - user-service auth failures"),
        LogEntry("2024-03-15T14:13:00Z", "ERROR", "notification-service", "Email delivery queue growing. 2,300 pending notifications."),
    ),
}

CASCADE_METRICS: Dict[str, Dict[str, MetricSnapshot]] = {
    "auth-service": {
        "error_rate": MetricSnapshot("auth-service", "error_rate", 95.0, 0.1, "%", "2024-03-15T14:05:00Z", "spike"),
        "latency": MetricSnapshot("auth-service", "latency_p99", 25.0, 15.0, "ms", "2024-03-15T14:05:00Z", "stable"),
        "cpu": MetricSnapshot("auth-service", "cpu", 22.0, 20.0, "%", "2024-03-15T14:05:00Z", "stable"),
    },
    "api-gateway": {
        "error_rate": MetricSnapshot("api-gateway", "error_rate", 65.0, 0.5, "%", "2024-03-15T14:07:00Z", "spike"),
        "latency": MetricSnapshot("api-gateway", "latency_p99", 180.0, 30.0, "ms", "2024-03-15T14:07:00Z", "rising"),
    },
    "user-service": {
        "error_rate": MetricSnapshot("user-service", "error_rate", 90.0, 0.1, "%", "2024-03-15T14:09:00Z", "spike"),
        "latency": MetricSnapshot("user-service", "latency_p99", 500.0, 45.0, "ms", "2024-03-15T14:09:00Z", "rising"),
    },
    "order-service": {
        "error_rate": MetricSnapshot("order-service", "error_rate", 48.0, 0.1, "%", "2024-03-15T14:11:00Z", "spike"),
        "latency": MetricSnapshot("order-service", "latency_p99", 2000.0, 80.0, "ms", "2024-03-15T14:11:00Z", "spike"),
    },
    "payment-service": {
        "error_rate": MetricSnapshot("payment-service", "error_rate", 52.0, 0.1, "%", "2024-03-15T14:12:00Z", "spike"),
        "latency": MetricSnapshot("payment-service", "latency_p99", 3000.0, 120.0, "ms", "2024-03-15T14:12:00Z", "spike"),
    },
    "notification-service": {
        "error_rate": MetricSnapshot("notification-service", "error_rate", 35.0, 0.1, "%", "2024-03-15T14:13:00Z", "rising"),
    },
}


def format_alerts(alerts: tuple[Alert, ...]) -> str:
    """Format alerts into a human-readable monitoring dashboard view."""
    lines = ["=" * 70, "  INCIDENT MONITORING DASHBOARD - ACTIVE ALERTS", "=" * 70, ""]
    for alert in alerts:
        icon = {"CRITICAL": "[!!!]", "WARNING": "[!!]", "INFO": "[i]"}.get(alert.severity, "[?]")
        lines.append(f"{icon} {alert.severity} | {alert.service} | {alert.title}")
        lines.append(f"    ID: {alert.alert_id} | Time: {alert.timestamp} | Status: {alert.status}")
        lines.append(f"    {alert.description}")
        lines.append("")
    lines.append(f"Total: {len(alerts)} active alerts")
    return "\n".join(lines)


def format_logs(logs: tuple[LogEntry, ...]) -> str:
    """Format log entries into a structured log view."""
    lines = ["-" * 60]
    for entry in logs:
        trace = f" [trace:{entry.trace_id}]" if entry.trace_id else ""
        lines.append(f"[{entry.level:5s}] {entry.timestamp} - {entry.message}{trace}")
    lines.append("-" * 60)
    return "\n".join(lines)


def format_metric(snapshot: MetricSnapshot) -> str:
    """Format a metric snapshot into a readable string."""
    delta = snapshot.current_value - snapshot.normal_value
    delta_pct = (delta / snapshot.normal_value * 100) if snapshot.normal_value > 0 else 0
    trend_icon = {"rising": "^", "falling": "v", "spike": "!!!", "stable": "-"}.get(snapshot.trend, "?")
    return (
        f"  {snapshot.metric_type}: {snapshot.current_value:.1f}{snapshot.unit} "
        f"(normal: {snapshot.normal_value:.1f}{snapshot.unit}, "
        f"delta: +{delta:.1f}{snapshot.unit} / +{delta_pct:.0f}%) [{trend_icon} {snapshot.trend}]"
    )


def format_metrics(metrics: Dict[str, MetricSnapshot]) -> str:
    """Format all metrics for a service."""
    lines = []
    for metric in metrics.values():
        lines.append(format_metric(metric))
    return "\n".join(lines)


def format_service_info(service: ServiceDefinition) -> str:
    """Format service details for inspection."""
    deps = ", ".join(service.dependencies) if service.dependencies else "none"
    return (
        f"Service: {service.name}\n"
        f"  Team: {service.team}\n"
        f"  Description: {service.description}\n"
        f"  Port: {service.port}\n"
        f"  Dependencies: {deps}\n"
        f"  Health Endpoint: {service.health_endpoint}\n"
        f"  Normal Latency: {service.normal_latency_ms}ms\n"
        f"  Normal Error Rate: {service.normal_error_rate * 100:.2f}%\n"
        f"  Normal CPU: {service.normal_cpu_pct}%\n"
        f"  Normal Memory: {service.normal_memory_pct}%"
    )


def format_dependency_map(service_names: tuple[str, ...]) -> str:
    """Format a dependency map for the given services."""
    lines = ["=" * 50, "  SERVICE DEPENDENCY MAP", "=" * 50, ""]
    for name in service_names:
        svc = SERVICES.get(name)
        if svc:
            deps = ", ".join(svc.dependencies) if svc.dependencies else "(no dependencies)"
            lines.append(f"  {svc.name} --> {deps}")
    lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)
