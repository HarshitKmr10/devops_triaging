---
title: ITSM Intelligence Environment
emoji: "🔧"
colorFrom: red
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
tags:
  - openenv
---

# ITSM Intelligence Environment - IT Service Management for LLM Agents

An OpenEnv-compliant environment that simulates **real-world IT Service Management (ITSM)** scenarios spanning DevOps incident response, service desk ticket triage, and infrastructure diagnostics. Agents investigate production incidents, triage support tickets, trace cascading failures, and execute remediations — exactly as a human SRE or service desk analyst would.

**Beyond evaluation** — this environment also ships with a complete **RL training pipeline**, **procedural scenario generator**, and **production data connectors** for training incident-response agents at scale.

## Motivation

Every organization runs on IT services. From production outages to VIP support escalations, effective ITSM requires systematic investigation, priority assessment under pressure, and decisive action. This environment benchmarks how well LLM agents handle the full ITSM spectrum across four tasks and three difficulty tiers.

But benchmarking alone isn't enough. To build agents that **improve over time**, you need:
1. An environment with dense reward signals (not just pass/fail)
2. Infinite diverse scenarios for training (not just 4 fixed ones)
3. A way to collect trajectories and convert them to training data
4. Integration with real production systems for deployment

This project provides all four.

## Tasks (Core Submission)

> These 4 tasks are what the hackathon validator runs. They are the default when you run `inference.py`.

| Task ID | Name | Difficulty | Description | Max Steps |
|---------|------|------------|-------------|-----------|
| `alert_triage` | Alert Triage | Easy | Classify severity, identify primary service, and escalate to the right team from 8 active alerts | 20 |
| `root_cause_analysis` | Root Cause Analysis | Medium | Diagnose a DB connection pool exhaustion caused by a missing index from a new deployment | 25 |
| `ticket_triage` | IT Service Ticket Triage | Medium | Process 6 support tickets, classify priority/category, identify VIP escalation, route to resolver groups | 25 |
| `cascading_failure` | Cascading Failure | Hard | Trace a 5-service cascading failure back to an auth-service config deployment that changed JWT key format | 30 |

### Task Details

#### Alert Triage (Easy)
A deployment to `payment-service` introduced a bug causing transaction failures. Multiple alerts fire across services. The agent must triage, classify the incident as P1, identify `payment-service` as the root, and escalate to `payments-team`.

#### Root Cause Analysis (Medium)
Deployment v2.5.1 to `order-service` added an inventory reconciliation query without an index on `inventory.sku` (2.3M rows). This causes sequential scans that exhaust the DB connection pool, leading to cascading timeouts. The agent must trace through logs and metrics to find the slow query, missing index, and execute remediation.

#### IT Service Ticket Triage (Medium)
A batch of 6 support tickets arrives simultaneously at the service desk. The agent must read each ticket, classify by category (access, hardware, network, software, change_request), assign priority (P1-P4), and route to the correct resolver group. One ticket is a VIP CEO escalation with a 90-minute SLA — the agent must identify it among routine requests and handle it first.

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
- **Penalties** (-0.01 to -0.05): Irrelevant actions, premature remediation, dangerous commands
- **Bonus** (+0.05): Tracing the full cascade chain (hard task)

Total possible reward per task: **1.0**

### Multi-Dimensional Scoring

Every episode produces a 5-axis score breakdown:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Investigation Depth | 0.20 | How thoroughly the agent explored logs, metrics, dependencies |
| Diagnosis Accuracy | 0.30 | Correctness of root cause identification |
| Resolution Quality | 0.25 | Correctness of remediation action |
| Safety Score | 0.15 | Avoided dangerous commands (`DROP`, `rm -rf`, premature remediation) |
| Efficiency | 0.10 | Steps used vs optimal path length |

### Danger Zone System

The environment penalizes unsafe actions:
- Destructive commands (`drop`, `delete`, `rm -rf`, `truncate`, `shutdown`) → -0.15 safety
- Premature remediation (acting before investigating) → -0.10 safety
- These are tracked and reported at episode end

## Setup

### Prerequisites
- Python 3.10+
- Docker (for containerized deployment)

### Local Development

```bash
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

### Run Inference (Default — Hackathon Submission)

```bash
export HF_TOKEN="your-hf-token"
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen3.5-122B-A10B-FP8"
export ENV_BASE_URL="http://localhost:8000"

python inference.py
```

This runs the **4 core tasks** and outputs `[START]/[STEP]/[END]` structured logs. Nothing else runs by default.

## Baseline Scores (Live HF Space)

Tested against `https://harshitkmr10-devops-triaging.hf.space`:

| Task | Score | Steps | Difficulty |
|------|-------|-------|------------|
| `alert_triage` | **0.910** | 6 | Easy |
| `root_cause_analysis` | **0.760** | 7 | Medium |
| `ticket_triage` | **0.820** | 14 | Medium |
| `cascading_failure` | **0.850** | 10 | Hard |
| **Mean** | **0.835** | | |

*Scores measured with scripted optimal agent on the live HF Space deployment.*

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/reset` | POST | Reset environment (pass `task_id` in body) |
| `/step` | POST | Execute an action |
| `/state` | GET | Get current state |
| `/ws` | WS | WebSocket for persistent sessions |
| `/schema` | GET | Action/observation schemas |

---

## RL Training & Production Pipeline

### Why This Matters

The core environment is an **evaluation benchmark**. But the real value of OpenEnv is enabling **RL training loops** where agents learn from experience:

```
┌──────────────────────────────────────────────────────────┐
│  EVALUATION (core submission)                            │
│  4 fixed tasks → LLM acts → score 0-1                   │
│  "How good is this model at incident response?"          │
│                                                          │
│  TRAINING (extended capabilities)                        │
│  Infinite generated scenarios → G rollouts → rank →      │
│  GRPO/DPO training → better model → re-evaluate          │
│  "Make this model BETTER at incident response"           │
└──────────────────────────────────────────────────────────┘
```

Our incremental reward signals (not just 0/1 at the end) are critical — they give RL algorithms dense gradient signal to learn from. The 5-axis scoring tells the training loop exactly WHERE the model is weak (investigation? diagnosis? safety?).

### 1. Procedural Scenario Generator (`generator/`)

Generates **infinite novel scenarios** from 8 composable failure types for RL training. No overfitting to 4 fixed tasks.

**8 Failure Types:**
| Type | Example |
|------|---------|
| `deployment_bug` | Code deployment introduces null pointer |
| `config_change` | Config update breaks validation logic |
| `resource_exhaustion` | Connection pool / memory / disk full |
| `dependency_failure` | External service becomes unreachable |
| `cert_expiry` | TLS certificate expires |
| `memory_leak` | Gradual OOM from memory leak |
| `dns_misconfiguration` | DNS change breaks service discovery |
| `rate_limit_breach` | Traffic spike overwhelms rate limits |

```python
from generator import ScenarioGenerator

gen = ScenarioGenerator()

# Generate a single scenario
scenario = gen.generate(seed=42, difficulty="medium")
# Play through it exactly like the core tasks
result = scenario.handle_action("view_alerts")

# Generate a batch for training
batch = gen.generate_batch(count=100, base_seed=0, difficulty="hard")
```

**Benchmark:** 30 generated scenarios average **0.630** reward with optimal agent (vs 0.835 for handcrafted core tasks).

### 2. GRPO Training Pipeline (`training/grpo_trainer.py`)

Full **Group Relative Policy Optimization** pipeline:
1. Generate scenario from the generator
2. Run **G rollouts** with the LLM (with temperature for diversity)
3. Rank rollouts by reward (best to worst)
4. Export as GRPO groups, DPO pairs, or SFT dataset
5. Train model to prefer high-reward trajectories

Includes **curriculum scheduling** that automatically advances difficulty when the agent masters the current level.

```python
from training.grpo_trainer import GRPOTrainer, GRPOConfig, create_random_llm_fn

config = GRPOConfig(
    model_name="Qwen/Qwen2.5-7B-Instruct",
    num_scenarios=100,
    rollouts_per_scenario=4,
)
trainer = GRPOTrainer(config)

# With real LLM:
# llm_fn = create_openai_llm_fn(base_url=..., api_key=..., model_name=...)

# For testing without LLM:
llm_fn = create_random_llm_fn()

stats = trainer.run_data_collection(llm_fn=llm_fn)
# Outputs: sft_dataset.jsonl, dpo_pairs.jsonl, grpo_groups.jsonl
```

**Benchmark:** 10 scenarios x 3 rollouts → 10 GRPO groups, 10 DPO pairs generated.

### 3. Trajectory Collector (`collector/`)

Records every agent run as structured training data.

```python
from collector import TrajectoryCollector

collector = TrajectoryCollector(output_dir="trajectories/")
traj = collector.start_trajectory(task_id="alert_triage", model_name="qwen-3.5")

# Record each step as the agent runs
collector.record_step(traj, observation, feedback, action_dict, reward, cumulative, done)

# Finish and auto-classify quality
collector.finish_trajectory(traj, total_reward=0.85, success=True)

# Export for different training methods
collector.export_sft_dataset("sft.jsonl", min_quality="good")     # Only good+ trajectories
collector.export_dpo_pairs("dpo.jsonl", reward_gap=0.2)            # Preference pairs
```

**Quality tiers:** expert (>0.8), good (>0.5), mediocre (>0.3), poor (<0.3)

### 4. Agent-in-the-Loop (`training/agent_loop.py`)

Autonomous investigation with **human approval gates** for remediation. The agent explores freely but must propose actions for review before executing.

```python
from training.agent_loop import AgentLoop, ApprovalStatus
from scenarios import CascadingFailureScenario

loop = AgentLoop(CascadingFailureScenario())

# Agent auto-investigates (safe actions only, no approval needed)
while not loop.investigation_complete:
    loop.auto_step()

# Agent proposes remediation → human reviews
proposal = loop.propose_remediation(
    service_name="auth-service",
    remediation="Rollback config to jwt-validation-v2",
    rationale="Config change caused JWT key format mismatch",
)
# proposal.confidence = 0.57, proposal.risk_level = "LOW"

# Human approves
loop.review_proposal(proposal.proposal_id, ApprovalStatus.APPROVED)
result = loop.execute_approved(proposal.proposal_id)
```

### 5. Runbook-to-Scenario Converter (`training/runbook_converter.py`)

Paste a **markdown runbook** → get a graded scenario. Any ops team can create training data from existing documentation.

```python
from training.runbook_converter import convert_runbook

scenario = convert_runbook("""
# Runbook: Payment Service High Error Rate

## Trigger
Payment service error rate exceeds 5%

## Severity: P1

## Services
- Primary: payment-service
- Affected: payment-service, api-gateway
- Team: payments-team

## Investigation Steps
1. Check alerts for payment-service -> Expect: error rate > 5%
2. Check logs on payment-service -> Expect: NullPointerException
3. Run diagnostic on payment-service -> Expect: recent deployment

## Root Cause
Keywords: deployment, bug, null pointer, release

## Remediation
Rollback the most recent deployment.
Keywords: rollback, revert, previous version
""")

# Play through it like any other scenario
result = scenario.handle_action("view_alerts")
```

**Benchmark:** Runbook-converted scenarios score **0.630** with optimal agent.

### 6. Production Data Connectors (`connectors/`)

Protocol-based interfaces for swapping mock data with live production systems.

| Connector | Data Source | Status |
|-----------|-----------|--------|
| `MockConnector` | Static scenario data | Working (default) |
| `PagerDutyConnector` | PagerDuty incidents/alerts | Ready (needs `PAGERDUTY_API_KEY`) |
| `DatadogConnector` | Datadog metrics/monitors | Ready (needs `DATADOG_API_KEY`) |
| `ELKConnector` | Elasticsearch/Loki logs | Ready (needs `ELASTICSEARCH_URL`) |
| `ServiceNowConnector` | ServiceNow ITSM tickets | Ready (needs credentials) |
| `JiraConnector` | Jira Cloud issues | Ready (needs `JIRA_API_TOKEN`) |
| `LinearConnector` | Linear issues | Ready (needs `LINEAR_API_KEY`) |

All connectors implement the same `AlertSource`, `LogSource`, `MetricSource` protocols — swap one line to go from mock to live:

```python
# Mock (default, for evaluation)
from connectors import MockConnector
source = MockConnector()

# Live (for production)
from connectors import PagerDutyConnector
source = PagerDutyConnector()

# Same interface either way
alerts = source.fetch_alerts()
```

## Full Architecture

```
devops-incident-env/
│
├── inference.py               # Hackathon submission entry point (4 core tasks)
├── models.py                  # IncidentAction, IncidentObservation, IncidentState
├── client.py                  # OpenEnv WebSocket client
├── openenv.yaml               # Environment manifest
├── pyproject.toml             # Dependencies
├── Dockerfile                 # Multi-stage build
├── web_ui.py                  # Gradio interactive demo
│
├── scenarios/                 # CORE: 4 handcrafted benchmark tasks
│   ├── base.py                #   BaseScenario with 5-axis scoring + danger zones
│   ├── alert_triage.py        #   Easy: alert classification
│   ├── root_cause_analysis.py #   Medium: DB pool exhaustion
│   ├── ticket_triage.py       #   Medium: ITSM ticket processing
│   └── cascading_failure.py   #   Hard: 5-service cascade
│
├── data/
│   └── service_topology.py    # 12 services, alerts, logs, metrics
│
├── server/
│   ├── app.py                 # FastAPI via openenv create_app
│   └── environment.py         # reset/step/state routing
│
├── generator/                 # EXTENDED: Infinite scenario generation
│   ├── failure_types.py       #   8 composable failure archetypes
│   └── scenario_generator.py  #   Seed-based procedural generation
│
├── training/                  # EXTENDED: RL training pipeline
│   ├── grpo_trainer.py        #   GRPO data collection + curriculum
│   ├── agent_loop.py          #   Agent-in-the-loop with approval gates
│   └── runbook_converter.py   #   Markdown runbook → graded scenario
│
├── collector/                 # EXTENDED: Training data collection
│   └── trajectory_collector.py #  SFT/DPO dataset export
│
└── connectors/                # EXTENDED: Production integrations
    ├── protocols.py           #   AlertSource, LogSource, MetricSource
    ├── mock.py                #   Default mock connector
    ├── pagerduty.py           #   PagerDuty alerts
    ├── datadog_connector.py   #   Datadog metrics
    ├── elk.py                 #   Elasticsearch/Loki logs
    └── ticket_systems.py      #   ServiceNow, Jira, Linear
```

## License

BSD-3-Clause
