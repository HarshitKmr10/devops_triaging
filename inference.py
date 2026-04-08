#!/usr/bin/env python3
"""
inference.py - DevOps Incident Response OpenEnv Agent
=====================================================
Runs an LLM agent through all 3 incident response tasks and emits structured logs.

Required environment variables:
    API_BASE_URL      LLM API endpoint (default: https://router.huggingface.co/v1)
    MODEL_NAME        Model identifier (default: Qwen/Qwen3.5-122B-A10B-FP8)
    HF_TOKEN          HuggingFace / API key (required)
    ENV_BASE_URL      Environment server URL (default: http://localhost:8000)

Stdout format:
    [START] task=<task> env=<benchmark> model=<model>
    [STEP]  step=<n> action=<action_json> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<0.000> rewards=<r1,r2,...>
"""

import json
import os
import re
import textwrap
from typing import List, Optional

from openai import OpenAI

from client import IncidentResponseClient
from models import IncidentAction

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HF_TOKEN = os.environ.get("HF_TOKEN") or os.environ.get("API_KEY")
if not HF_TOKEN:
    raise EnvironmentError("HF_TOKEN environment variable is required")
API_KEY = HF_TOKEN
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3.5-122B-A10B-FP8")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:8000")
IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
BENCHMARK = "devops_incident_response"

MAX_STEPS_PER_TASK = {
    "alert_triage": 12,
    "root_cause_analysis": 18,
    "cascading_failure": 25,
    "ticket_triage": 20,
}

SUCCESS_SCORE_THRESHOLD = 0.4
TEMPERATURE = 0.2
MAX_TOKENS = 2048

TASKS = [
    "alert_triage",
    "root_cause_analysis",
    "cascading_failure",
    "ticket_triage",
]

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert Site Reliability Engineer (SRE) responding to a production incident.
    You have access to the following tools to investigate and resolve the incident:

    INVESTIGATION ACTIONS:
    - view_alerts: View all active monitoring alerts
    - query_logs: Search service logs (provide service_name, optional keyword)
    - query_metrics: Get service metrics (provide service_name, optional metric_type: cpu/memory/latency/error_rate/connections)
    - inspect_service: Get service details and configuration (provide service_name)
    - check_dependencies: View the service dependency map
    - run_diagnostic: Run diagnostics on a service (provide service_name)

    RESOLUTION ACTIONS:
    - classify_severity: Classify incident severity (provide severity: P1/P2/P3/P4)
    - identify_root_cause: Declare root cause (provide service_name and root_cause description)
    - execute_remediation: Apply fix (provide service_name and remediation description)
    - escalate: Escalate to team (provide team name)

    RESPONSE FORMAT - You MUST respond with valid JSON only:
    {
        "action_type": "<action_name>",
        "service_name": "<service>",
        "keyword": "<search_term>",
        "metric_type": "<metric>",
        "severity": "<P1-P4>",
        "root_cause": "<description>",
        "remediation": "<description>",
        "team": "<team_name>"
    }

    Only include fields relevant to the action. Always start with view_alerts to understand
    the situation, then systematically investigate before concluding.
    Respond with ONLY the JSON object, no other text.
""").strip()


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# LLM action extraction
# ---------------------------------------------------------------------------

def parse_action_json(text: str) -> dict:
    """Extract a JSON action object from LLM output, handling think tags and markdown."""
    # Strip think/reasoning tags
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Try to find JSON in markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: default action
    return {"action_type": "view_alerts"}


def get_model_action(
    client: OpenAI,
    observation: str,
    feedback: str,
    history: List[str],
) -> dict:
    """Query the LLM for the next action."""
    history_block = "\n".join(history[-5:]) if history else "None"
    user_prompt = (
        f"CURRENT OBSERVATION:\n{observation}\n\n"
        f"FEEDBACK: {feedback}\n\n"
        f"ACTION HISTORY:\n{history_block}\n\n"
        f"What is your next action? Respond with JSON only."
    )

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        raw = (completion.choices[0].message.content or "").strip()
        return parse_action_json(raw)

    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return {"action_type": "view_alerts"}


# ---------------------------------------------------------------------------
# Single task runner
# ---------------------------------------------------------------------------

def run_task(llm_client: OpenAI, task_name: str) -> None:
    """Run one full episode, emitting [START]/[STEP]/[END] logs."""
    if IMAGE_NAME:
        env_instance = IncidentResponseClient.from_docker_image(IMAGE_NAME, task=task_name)
    else:
        env_instance = IncidentResponseClient(base_url=ENV_BASE_URL)

    history: List[str] = []
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    last_error: Optional[str] = None
    max_steps = MAX_STEPS_PER_TASK.get(task_name, 15)

    log_start(task=task_name, env=BENCHMARK, model=MODEL_NAME)

    try:
        with env_instance.sync() as env:
            result = env.reset(task_id=task_name)

            for step in range(1, max_steps + 1):
                if result.done:
                    break

                obs_text = result.observation.output
                feedback_text = result.observation.feedback

                action_dict = get_model_action(llm_client, obs_text, feedback_text, history)
                action_type = action_dict.get("action_type", "view_alerts")

                try:
                    action = IncidentAction(**action_dict)
                    result = env.step(action)
                    last_error = None
                except Exception as exc:
                    last_error = str(exc)
                    log_step(step=step, action=action_type, reward=0.0, done=True, error=last_error)
                    steps_taken = step
                    break

                reward = result.reward or 0.0
                done = result.done

                rewards.append(reward)
                steps_taken = step

                log_step(step=step, action=action_type, reward=reward, done=done, error=last_error)
                history.append(f"Step {step}: {action_type} -> reward={reward:.2f}")

                if done:
                    break

        # Score is cumulative reward (already clamped to [0.0, 1.0] by scenario)
        score = min(sum(rewards), 1.0) if rewards else 0.0
        score = max(1e-6, min(score, 1 - 1e-6))
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as exc:
        print(f"[DEBUG] Task {task_name} error: {exc}", flush=True)
        last_error = str(exc)

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    llm_client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    for task_name in TASKS:
        run_task(llm_client, task_name)


if __name__ == "__main__":
    main()
