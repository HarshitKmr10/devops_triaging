import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TrajectoryStep:
    """A single step in a trajectory."""

    step_number: int
    observation: str
    feedback: str
    action: Dict[str, Any]
    reward: float
    cumulative_reward: float
    done: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class Trajectory:
    """A complete episode trajectory."""

    trajectory_id: str
    task_id: str
    difficulty: str
    model_name: str
    steps: List[TrajectoryStep] = field(default_factory=list)
    total_reward: float = 0.0
    success: bool = False
    score_breakdown: Optional[Dict[str, float]] = None
    safety_violations: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def num_steps(self) -> int:
        return len(self.steps)

    @property
    def duration_seconds(self) -> float:
        if self.end_time > 0:
            return self.end_time - self.start_time
        return 0.0

    @property
    def quality_tier(self) -> str:
        """Classify trajectory quality for filtering."""
        if self.total_reward >= 0.8:
            return "expert"
        elif self.total_reward >= 0.5:
            return "good"
        elif self.total_reward >= 0.3:
            return "mediocre"
        return "poor"

    def to_conversation_format(self) -> List[Dict[str, str]]:
        """Convert to chat conversation format for SFT training."""
        messages: list[Dict[str, str]] = []
        messages.append({
            "role": "system",
            "content": (
                "You are an expert SRE responding to a production incident. "
                "Investigate systematically using available tools and resolve the issue."
            ),
        })

        for step in self.steps:
            # User message = observation + feedback
            user_content = step.observation
            if step.feedback:
                user_content += f"\n\nFeedback: {step.feedback}"
            messages.append({"role": "user", "content": user_content})

            # Assistant message = action taken
            action_json = json.dumps(step.action, indent=2)
            messages.append({"role": "assistant", "content": action_json})

        return messages

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "trajectory_id": self.trajectory_id,
            "task_id": self.task_id,
            "difficulty": self.difficulty,
            "model_name": self.model_name,
            "total_reward": self.total_reward,
            "success": self.success,
            "quality_tier": self.quality_tier,
            "num_steps": self.num_steps,
            "duration_seconds": self.duration_seconds,
            "score_breakdown": self.score_breakdown,
            "safety_violations": self.safety_violations,
            "steps": [asdict(s) for s in self.steps],
            "conversation": self.to_conversation_format(),
            "metadata": self.metadata,
        }


class TrajectoryCollector:

    def __init__(self, output_dir: str = "trajectories") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._trajectories: List[Trajectory] = []
        self._active: Dict[str, Trajectory] = {}
        self._counter = 0

    @property
    def trajectories(self) -> List[Trajectory]:
        return list(self._trajectories)

    def start_trajectory(
        self,
        task_id: str,
        model_name: str = "unknown",
        difficulty: str = "medium",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Trajectory:
        """Start recording a new trajectory."""
        self._counter += 1
        traj_id = f"traj_{task_id}_{self._counter}_{int(time.time())}"

        traj = Trajectory(
            trajectory_id=traj_id,
            task_id=task_id,
            difficulty=difficulty,
            model_name=model_name,
            metadata=metadata or {},
        )
        self._active[traj_id] = traj
        return traj

    def record_step(
        self,
        trajectory: Trajectory,
        observation: str,
        feedback: str,
        action: Dict[str, Any],
        reward: float,
        cumulative_reward: float,
        done: bool,
    ) -> None:
        """Record a single step in the trajectory."""
        step = TrajectoryStep(
            step_number=len(trajectory.steps) + 1,
            observation=observation,
            feedback=feedback,
            action=action,
            reward=reward,
            cumulative_reward=cumulative_reward,
            done=done,
        )
        trajectory.steps.append(step)

    def finish_trajectory(
        self,
        trajectory: Trajectory,
        total_reward: float,
        success: bool,
        score_breakdown: Optional[Dict[str, float]] = None,
        safety_violations: Optional[List[str]] = None,
    ) -> None:
        """Finish and store a trajectory."""
        trajectory.total_reward = total_reward
        trajectory.success = success
        trajectory.end_time = time.time()
        trajectory.score_breakdown = score_breakdown
        trajectory.safety_violations = safety_violations or []

        self._trajectories.append(trajectory)
        self._active.pop(trajectory.trajectory_id, None)

        # Auto-save individual trajectory
        traj_path = self._output_dir / f"{trajectory.trajectory_id}.json"
        with open(traj_path, "w") as f:
            json.dump(trajectory.to_dict(), f, indent=2)

    def export_sft_dataset(
        self,
        output_path: str,
        min_quality: str = "good",
    ) -> int:
        quality_order = {"expert": 3, "good": 2, "mediocre": 1, "poor": 0}
        min_level = quality_order.get(min_quality, 2)

        count = 0
        with open(output_path, "w") as f:
            for traj in self._trajectories:
                tier_level = quality_order.get(traj.quality_tier, 0)
                if tier_level >= min_level:
                    record = {
                        "messages": traj.to_conversation_format(),
                        "task_id": traj.task_id,
                        "difficulty": traj.difficulty,
                        "total_reward": traj.total_reward,
                        "quality_tier": traj.quality_tier,
                    }
                    f.write(json.dumps(record) + "\n")
                    count += 1

        return count

    def export_dpo_pairs(
        self,
        output_path: str,
        reward_gap: float = 0.2,
    ) -> int:
        # Group by task
        by_task: Dict[str, List[Trajectory]] = {}
        for traj in self._trajectories:
            by_task.setdefault(traj.task_id, []).append(traj)

        count = 0
        with open(output_path, "w") as f:
            for task_id, trajs in by_task.items():
                sorted_trajs = sorted(trajs, key=lambda t: t.total_reward, reverse=True)
                for i, chosen in enumerate(sorted_trajs):
                    for rejected in sorted_trajs[i + 1:]:
                        if chosen.total_reward - rejected.total_reward >= reward_gap:
                            pair = {
                                "task_id": task_id,
                                "chosen": chosen.to_conversation_format(),
                                "rejected": rejected.to_conversation_format(),
                                "chosen_reward": chosen.total_reward,
                                "rejected_reward": rejected.total_reward,
                            }
                            f.write(json.dumps(pair) + "\n")
                            count += 1

        return count

    def export_statistics(self) -> Dict[str, Any]:
        """Get collection statistics."""
        if not self._trajectories:
            return {"count": 0}

        rewards = [t.total_reward for t in self._trajectories]
        tiers = {}
        for t in self._trajectories:
            tiers[t.quality_tier] = tiers.get(t.quality_tier, 0) + 1

        return {
            "count": len(self._trajectories),
            "mean_reward": sum(rewards) / len(rewards),
            "min_reward": min(rewards),
            "max_reward": max(rewards),
            "success_rate": sum(1 for t in self._trajectories if t.success) / len(self._trajectories),
            "quality_distribution": tiers,
            "tasks": list(set(t.task_id for t in self._trajectories)),
            "models": list(set(t.model_name for t in self._trajectories)),
        }
