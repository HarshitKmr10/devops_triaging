# DevOps Incident Response Environment

An OpenEnv-compliant environment that simulates **real-world SRE incident response** scenarios. Agents investigate production incidents by querying alerts, logs, metrics, tracing service dependencies, and executing remediations — exactly as a human on-call engineer would.

## Motivation

Every tech company faces production incidents. Effective incident response requires systematic investigation, pattern recognition across noisy data, and decisive action under pressure. This environment benchmarks how well LLM agents handle these real-world challenges across three difficulty tiers.

## Tasks

| Task ID | Name | Difficulty | Description | Max Steps |
|---------|------|------------|-------------|-----------|
| `alert_triage` | Alert Triage | Easy | Classify severity, identify primary service, and escalate to the right team from 8 active alerts | 20 |
| `root_cause_analysis` | Root Cause Analysis | Medium | Diagnose a DB connection pool exhaustion caused by a missing index from a new deployment | 25 |
| `cascading_failure` | Cascading Failure | Hard | Trace a 5-service cascading failure back to an auth-service config deployment that changed JWT key format | 30 |

### Task Details

#### Alert Triage (Easy)
A deployment to `payment-service` introduced a bug causing transaction failures. Multiple alerts fire across services. The agent must triage, classify the incident as P1, identify `payment-service` as the root, and escalate to `payments-team`.

#### Root Cause Analysis (Medium)
Deployment v2.5.1 to `order-service` added an inventory reconciliation query without an index on `inventory.sku` (2.3M rows). This causes sequential scans that exhaust the DB connection pool, leading to cascading timeouts. The agent must trace through logs and metrics to find the slow query, missing index, and execute remediation.

#### Cascading Failure (Hard)
A config deployment to `auth-service` changed the JWT key_id format from `rsa-prod-2024` to `rsa_prod_2024`. This causes 95% token rejection, cascading through: `auth-service` -> `api-gateway` -> `user-service` -> `order-service` -> `payment-service`. The agent must trace backwards through the chain and rollback the config.

## Action Space

| Action | Parameters | Description |
|--------|-----------|-------------|
| `view_alerts` | — | View all active monitoring alerts |
| `query_logs` | `service_name`, `keyword` (opt) | Search service logs, optionally filter by keyword |
| `query_metrics` | `service_name`, `metric_type` (opt) | Get service metrics (cpu, memory, latency, error_rate, connections) |
| `inspect_service` | `service_name` | Get service details, team ownership, dependencies |
| `check_dependencies` | — | View the full service dependency map |
| `run_diagnostic` | `service_name` | Run detailed diagnostics on a service |
| `classify_severity` | `severity` (P1-P4) | Classify the incident severity level |
| `identify_root_cause` | `service_name`, `root_cause` | Declare the root cause of the incident |
| `execute_remediation` | `service_name`, `remediation` | Execute a remediation action |
| `escalate` | `team` | Escalate the incident to a team |

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `output` | string | Primary output from the action (logs, metrics, alerts, etc.) |
| `system_status` | string | Current overall system health |
| `active_alerts_count` | int | Number of active alerts |
| `feedback` | string | Feedback on the agent's action quality |
| `task_description` | string | What the agent needs to accomplish |
| `available_actions` | list[str] | Valid action types |
| `services` | list[str] | Available services to investigate |
| `step_number` | int | Current step in the episode |
| `max_steps` | int | Maximum allowed steps |
| `reward` | float | Reward for the current step (0.0-1.0) |
| `done` | bool | Whether the episode has ended |

## Reward Design

Rewards are **incremental throughout the trajectory** (not just at completion):

- **Investigation rewards** (+0.02 to +0.10): Querying relevant logs, metrics, diagnostics
- **Milestone rewards** (+0.05 to +0.25): Correct severity classification, root cause identification
- **Resolution rewards** (+0.15 to +0.25): Correct remediation executed
- **Penalties** (-0.01 to -0.02): Irrelevant actions, premature remediation attempts
- **Bonus** (+0.05): Tracing the full cascade chain (hard task)

Total possible reward per task: **1.0**

## Setup

### Prerequisites
- Python 3.10+
- Docker (for containerized deployment)

### Local Development

```bash
# Clone and install
cd devops-incident-env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start server
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker build -t devops-incident-env:latest .
docker run --rm -p 8000:8000 devops-incident-env:latest
```

### Run Inference

```bash
export HF_TOKEN="your-hf-token"
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export ENV_BASE_URL="http://localhost:8000"

python inference.py
```

## Baseline Scores

| Model | alert_triage | root_cause_analysis | cascading_failure | Mean |
|-------|-------------|--------------------|--------------------|------|
| Qwen2.5-72B | ~0.65 | ~0.55 | ~0.45 | ~0.55 |

*Scores vary by model capability. Investigation-heavy tasks reward systematic exploration.*

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/reset` | POST | Reset environment (pass `task_id` in body) |
| `/step` | POST | Execute an action |
| `/state` | GET | Get current state |
| `/ws` | WS | WebSocket for persistent sessions |
| `/web` | GET | Interactive web interface |

## Hugging Face Deployment

```bash
# Using OpenEnv CLI
openenv push --repo-id your-org/devops-incident-response --private
```

## Architecture

```
devops-incident-env/
├── models.py              # IncidentAction, IncidentObservation, IncidentState
├── client.py              # EnvClient subclass for WebSocket interaction
├── inference.py           # Baseline LLM agent with structured logging
├── openenv.yaml           # Environment manifest
├── pyproject.toml         # Dependencies
├── Dockerfile             # Multi-stage build on openenv-base
├── scenarios/
│   ├── base.py            # Abstract BaseScenario with reward shaping
│   ├── alert_triage.py    # Easy: alert classification and routing
│   ├── root_cause_analysis.py  # Medium: DB pool exhaustion diagnosis
│   └── cascading_failure.py    # Hard: 5-service cascade tracing
├── data/
│   └── service_topology.py     # Service definitions, alert/log/metric data
└── server/
    ├── app.py             # FastAPI app via openenv create_app
    └── environment.py     # Core Environment with reset/step/state
```

## License

BSD-3-Clause
