import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from generator.scenario_generator import ScenarioGenerator, GeneratedScenario
from collector.trajectory_collector import TrajectoryCollector, Trajectory

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RolloutResult:
    """Result of a single rollout (agent playing through a scenario)."""

    scenario_id: str
    trajectory: Trajectory
    total_reward: float
    score_breakdown: Dict[str, float]
    conversation: List[Dict[str, str]]
    actions_taken: List[str]


@dataclass
class GRPOConfig:
    """Configuration for GRPO training."""

    # Model
    model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    base_url: str = "https://router.huggingface.co/v1"
    api_key: str = ""

    # Training
    num_scenarios: int = 100
    rollouts_per_scenario: int = 4  # G in GRPO
    epochs: int = 3
    learning_rate: float = 1e-5
    batch_size: int = 4
    max_steps_per_episode: int = 20

    # Curriculum
    start_difficulty: str = "easy"
    difficulty_threshold: float = 0.7  # Advance when avg score exceeds this
    difficulties: Tuple[str, ...] = ("easy", "medium", "hard")

    # Output
    output_dir: str = "./training_output"
    save_trajectories: bool = True
    log_interval: int = 10

    # Scenario generation
    base_seed: int = 42
    failure_types: Optional[List[str]] = None  # None = all types


class CurriculumScheduler:
    """Manages progressive difficulty scaling."""

    def __init__(self, config: GRPOConfig) -> None:
        self._difficulties = config.difficulties
        self._threshold = config.difficulty_threshold
        self._current_idx = self._difficulties.index(config.start_difficulty)
        self._scores_window: List[float] = []
        self._window_size = 20

    @property
    def current_difficulty(self) -> str:
        return self._difficulties[self._current_idx]

    @property
    def at_max_difficulty(self) -> bool:
        return self._current_idx >= len(self._difficulties) - 1

    def record_score(self, score: float) -> None:
        """Record a score and potentially advance difficulty."""
        self._scores_window.append(score)
        if len(self._scores_window) > self._window_size:
            self._scores_window = self._scores_window[-self._window_size:]

    def should_advance(self) -> bool:
        """Check if we should move to the next difficulty."""
        if self.at_max_difficulty:
            return False
        if len(self._scores_window) < self._window_size // 2:
            return False
        avg = sum(self._scores_window) / len(self._scores_window)
        return avg >= self._threshold

    def advance(self) -> str:
        """Advance to next difficulty. Returns new difficulty."""
        if not self.at_max_difficulty:
            self._current_idx += 1
            self._scores_window.clear()
        return self.current_difficulty

    def get_status(self) -> Dict[str, Any]:
        avg = sum(self._scores_window) / len(self._scores_window) if self._scores_window else 0.0
        return {
            "current_difficulty": self.current_difficulty,
            "window_avg_score": round(avg, 3),
            "window_size": len(self._scores_window),
            "threshold": self._threshold,
            "at_max": self.at_max_difficulty,
        }


class GRPORolloutEngine:

    def __init__(self, config: GRPOConfig) -> None:
        self._config = config
        self._generator = ScenarioGenerator()
        self._collector = TrajectoryCollector(
            output_dir=os.path.join(config.output_dir, "trajectories")
        )

    def generate_rollouts(
        self,
        scenario_seed: int,
        difficulty: str,
        num_rollouts: int,
        llm_fn: Any,  # Callable that takes (observation, feedback, history) -> action_dict
    ) -> List[RolloutResult]:
        results: List[RolloutResult] = []

        for rollout_idx in range(num_rollouts):
            # Create fresh scenario instance for each rollout
            scenario = self._generator.generate(
                seed=scenario_seed,
                difficulty=difficulty,
            )

            traj = self._collector.start_trajectory(
                task_id=scenario.config.task_id,
                model_name=self._config.model_name,
                difficulty=difficulty,
                metadata={"rollout_idx": rollout_idx, "seed": scenario_seed},
            )

            history: List[str] = []
            cumulative_reward = 0.0

            # Initial observation
            cfg = scenario.config
            observation = (
                f"INCIDENT: {cfg.task_name}\n"
                f"Status: {cfg.system_status}\n"
                f"Services: {', '.join(cfg.services)}\n\n"
                f"{cfg.description}"
            )
            feedback = "Begin investigation."

            for step in range(self._config.max_steps_per_episode):
                # Get LLM action
                action_dict = llm_fn(observation, feedback, history)
                action_type = action_dict.get("action_type", "view_alerts")

                # Execute in environment
                result = scenario.handle_action(**action_dict)
                cumulative_reward += result.reward

                # Record
                self._collector.record_step(
                    traj,
                    observation=observation[:500],
                    feedback=feedback,
                    action=action_dict,
                    reward=result.reward,
                    cumulative_reward=cumulative_reward,
                    done=result.done,
                )

                history.append(f"Step {step + 1}: {action_type} -> reward={result.reward:.2f}")
                observation = result.output or feedback
                feedback = result.feedback

                if result.done or scenario.is_done:
                    break

            # Finish trajectory
            bd = scenario.get_score_breakdown()
            self._collector.finish_trajectory(
                traj,
                total_reward=scenario.total_reward,
                success=scenario.total_reward >= 0.5,
                score_breakdown={
                    "investigation": bd.investigation,
                    "diagnosis": bd.diagnosis,
                    "resolution": bd.resolution,
                    "safety": bd.safety,
                    "efficiency": bd.efficiency,
                    "weighted_total": bd.total,
                },
                safety_violations=scenario.safety_violations,
            )

            results.append(RolloutResult(
                scenario_id=scenario.config.task_id,
                trajectory=traj,
                total_reward=scenario.total_reward,
                score_breakdown={
                    "investigation": bd.investigation,
                    "diagnosis": bd.diagnosis,
                    "resolution": bd.resolution,
                    "safety": bd.safety,
                },
                conversation=traj.to_conversation_format(),
                actions_taken=scenario.actions_taken,
            ))

        # Sort by reward (best first)
        results.sort(key=lambda r: r.total_reward, reverse=True)
        return results

    @property
    def collector(self) -> TrajectoryCollector:
        return self._collector


class GRPOTrainer:

    def __init__(self, config: GRPOConfig) -> None:
        self._config = config
        self._engine = GRPORolloutEngine(config)
        self._curriculum = CurriculumScheduler(config)
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Training log
        self._log: List[Dict[str, Any]] = []

    def run_data_collection(
        self,
        llm_fn: Any,
        num_scenarios: Optional[int] = None,
    ) -> Dict[str, Any]:
        n_scenarios = num_scenarios or self._config.num_scenarios
        all_results: List[List[RolloutResult]] = []

        log.info("Starting GRPO data collection: %d scenarios x %d rollouts", n_scenarios, self._config.rollouts_per_scenario)
        log.info("Initial difficulty: %s", self._curriculum.current_difficulty)

        for i in range(n_scenarios):
            seed = self._config.base_seed + i
            difficulty = self._curriculum.current_difficulty

            # Generate rollouts
            rollouts = self._engine.generate_rollouts(
                scenario_seed=seed,
                difficulty=difficulty,
                num_rollouts=self._config.rollouts_per_scenario,
                llm_fn=llm_fn,
            )

            all_results.append(rollouts)

            # Track best rollout score for curriculum
            best_score = rollouts[0].total_reward if rollouts else 0.0
            self._curriculum.record_score(best_score)

            # Log progress
            if (i + 1) % self._config.log_interval == 0:
                status = self._curriculum.get_status()
                log.info(
                    "[%d/%d] difficulty=%s avg_score=%.3f best_this=%.3f",
                    i + 1, n_scenarios, status['current_difficulty'],
                    status['window_avg_score'], best_score,
                )

            # Curriculum advancement
            if self._curriculum.should_advance():
                old = self._curriculum.current_difficulty
                new = self._curriculum.advance()
                log.info("Curriculum advanced: %s -> %s", old, new)

            self._log.append({
                "scenario_idx": i,
                "seed": seed,
                "difficulty": difficulty,
                "num_rollouts": len(rollouts),
                "best_reward": best_score,
                "worst_reward": rollouts[-1].total_reward if rollouts else 0.0,
                "reward_gap": (rollouts[0].total_reward - rollouts[-1].total_reward) if len(rollouts) > 1 else 0.0,
            })

        # Export datasets
        collector = self._engine.collector
        sft_path = str(self._output_dir / "sft_dataset.jsonl")
        dpo_path = str(self._output_dir / "dpo_pairs.jsonl")
        grpo_path = str(self._output_dir / "grpo_groups.jsonl")

        sft_count = collector.export_sft_dataset(sft_path, min_quality="good")
        dpo_count = collector.export_dpo_pairs(dpo_path, reward_gap=0.15)

        # Export GRPO groups (all G rollouts per scenario, ranked)
        grpo_count = self._export_grpo_groups(all_results, grpo_path)

        # Save training log
        log_path = self._output_dir / "training_log.json"
        with open(log_path, "w") as f:
            json.dump(self._log, f, indent=2)

        stats = collector.export_statistics()
        stats.update({
            "sft_exported": sft_count,
            "dpo_pairs": dpo_count,
            "grpo_groups": grpo_count,
            "curriculum_final": self._curriculum.get_status(),
        })

        # Save stats
        with open(self._output_dir / "collection_stats.json", "w") as f:
            json.dump(stats, f, indent=2)

        log.info("Collection complete! Trajectories=%d SFT=%d DPO=%d GRPO=%d output=%s",
                 stats['count'], sft_count, dpo_count, grpo_count, self._output_dir)

        return stats

    def _export_grpo_groups(
        self,
        all_results: List[List[RolloutResult]],
        output_path: str,
    ) -> int:
        count = 0
        with open(output_path, "w") as f:
            for group in all_results:
                if len(group) < 2:
                    continue
                record = {
                    "scenario_id": group[0].scenario_id,
                    "rollouts": [
                        {
                            "conversation": r.conversation,
                            "total_reward": r.total_reward,
                            "actions": r.actions_taken,
                            "score_breakdown": r.score_breakdown,
                        }
                        for r in group
                    ],
                    "best_reward": group[0].total_reward,
                    "worst_reward": group[-1].total_reward,
                    "reward_gap": group[0].total_reward - group[-1].total_reward,
                }
                f.write(json.dumps(record) + "\n")
                count += 1
        return count


def create_openai_llm_fn(
    base_url: str,
    api_key: str,
    model_name: str,
    temperature: float = 0.7,
) -> Any:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)

    system_prompt = (
        "You are an expert SRE responding to a production incident. "
        "You have these actions: view_alerts, query_logs, query_metrics, "
        "inspect_service, check_dependencies, run_diagnostic, classify_severity, "
        "identify_root_cause, execute_remediation, escalate. "
        "Respond with ONLY a JSON object: {\"action_type\": \"...\", ...}"
    )

    def llm_fn(observation: str, feedback: str, history: List[str]) -> Dict[str, Any]:
        import re
        history_text = "\n".join(history[-5:]) if history else "None"
        prompt = f"Observation:\n{observation}\n\nFeedback: {feedback}\n\nHistory:\n{history_text}\n\nNext action (JSON):"

        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=512,
            )
            text = (resp.choices[0].message.content or "").strip()
            # Strip think tags
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
            # Find JSON
            match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            log.error("LLM request failed: %s", e)

        return {"action_type": "view_alerts"}

    return llm_fn


def create_random_llm_fn() -> Any:
    """Create a random action function for testing (no LLM needed)."""
    import random as _random

    action_types = [
        "view_alerts", "query_logs", "query_metrics",
        "inspect_service", "check_dependencies", "run_diagnostic",
        "classify_severity", "identify_root_cause", "execute_remediation",
    ]
    services = ["auth-service", "api-gateway", "order-service", "payment-service", "user-service"]

    def random_fn(observation: str, feedback: str, history: List[str]) -> Dict[str, Any]:
        action_type = _random.choice(action_types)
        result: Dict[str, Any] = {"action_type": action_type}
        if action_type in ("query_logs", "query_metrics", "inspect_service", "run_diagnostic"):
            result["service_name"] = _random.choice(services)
        elif action_type == "classify_severity":
            result["severity"] = _random.choice(["P1", "P2", "P3"])
        elif action_type == "identify_root_cause":
            result["service_name"] = _random.choice(services)
            result["root_cause"] = "deployment caused failure"
        elif action_type == "execute_remediation":
            result["service_name"] = _random.choice(services)
            result["remediation"] = "rollback to previous version"
        return result

    return random_fn


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GRPO Training for Incident Response")
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--base_url", default="https://router.huggingface.co/v1")
    parser.add_argument("--api_key", default=os.getenv("HF_TOKEN", ""))
    parser.add_argument("--num_scenarios", type=int, default=50)
    parser.add_argument("--rollouts", type=int, default=4)
    parser.add_argument("--output_dir", default="./training_output")
    parser.add_argument("--random", action="store_true", help="Use random agent (no LLM)")
    args = parser.parse_args()

    config = GRPOConfig(
        model_name=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        num_scenarios=args.num_scenarios,
        rollouts_per_scenario=args.rollouts,
        output_dir=args.output_dir,
    )

    trainer = GRPOTrainer(config)

    if args.random:
        llm_fn = create_random_llm_fn()
    else:
        llm_fn = create_openai_llm_fn(
            base_url=config.base_url,
            api_key=config.api_key,
            model_name=config.model_name,
        )

    stats = trainer.run_data_collection(llm_fn=llm_fn)
    log.info("Final stats: %s", json.dumps(stats, indent=2))
