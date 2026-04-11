import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from scenarios.base import BaseScenario, ScenarioConfig


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


@dataclass
class RemediationProposal:
    """A proposed remediation action awaiting human approval."""

    proposal_id: str
    action_type: str
    service_name: str
    remediation: str
    confidence: float  # 0.0 - 1.0
    risk_level: str   # LOW, MEDIUM, HIGH, CRITICAL
    reversible: bool
    rationale: str
    evidence: List[str]
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_notes: str = ""
    modified_action: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class InvestigationState:
    """Tracks the agent's investigation progress."""

    services_queried: List[str] = field(default_factory=list)
    alerts_reviewed: bool = False
    dependencies_checked: bool = False
    diagnostics_run: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    suspected_root_cause: Optional[str] = None
    severity_classification: Optional[str] = None
    investigation_depth: float = 0.0  # 0.0 - 1.0


def assess_risk(
    action_type: str,
    remediation: str,
    service_name: str,
) -> Tuple[str, bool]:
    rem_lower = remediation.lower()

    # High-risk patterns
    high_risk = ["delete", "drop", "truncate", "destroy", "format", "shutdown"]
    if any(p in rem_lower for p in high_risk):
        return "CRITICAL", False

    # Medium-risk patterns
    medium_risk = ["restart", "redeploy", "migrate", "scale down", "reduce"]
    if any(p in rem_lower for p in medium_risk):
        return "MEDIUM", True

    # Low-risk / reversible patterns
    low_risk = ["rollback", "revert", "increase", "scale up", "add", "enable"]
    if any(p in rem_lower for p in low_risk):
        return "LOW", True

    return "MEDIUM", True


def compute_confidence(
    investigation: InvestigationState,
    root_cause_specificity: int,
) -> float:
    score = 0.0

    # Investigation breadth
    if investigation.alerts_reviewed:
        score += 0.15
    if investigation.dependencies_checked:
        score += 0.10
    score += min(0.25, len(investigation.services_queried) * 0.05)
    score += min(0.15, len(investigation.diagnostics_run) * 0.05)
    score += min(0.10, len(investigation.findings) * 0.02)

    # Root cause specificity
    score += min(0.25, root_cause_specificity * 0.05)

    return min(1.0, score)


class AgentLoop:

    def __init__(
        self,
        scenario: BaseScenario,
        llm_fn: Optional[Callable] = None,
    ) -> None:
        self._scenario = scenario
        self._llm_fn = llm_fn
        self._investigation = InvestigationState()
        self._proposals: Dict[str, RemediationProposal] = {}
        self._history: List[Dict[str, Any]] = []
        self._proposal_counter = 0

        # Auto-investigation actions (safe, no approval needed)
        self._safe_actions = frozenset({
            "view_alerts", "query_logs", "query_metrics",
            "inspect_service", "check_dependencies", "run_diagnostic",
            "classify_severity",
        })

        # Actions requiring approval
        self._approval_actions = frozenset({
            "execute_remediation", "escalate", "identify_root_cause",
        })

    @property
    def investigation(self) -> InvestigationState:
        return self._investigation

    @property
    def proposals(self) -> List[RemediationProposal]:
        return list(self._proposals.values())

    @property
    def pending_proposals(self) -> List[RemediationProposal]:
        return [p for p in self._proposals.values() if p.status == ApprovalStatus.PENDING]

    @property
    def investigation_complete(self) -> bool:
        """Check if the agent has done sufficient investigation."""
        inv = self._investigation
        return (
            inv.alerts_reviewed
            and len(inv.services_queried) >= 2
            and inv.investigation_depth >= 0.5
        )

    def auto_step(self, observation: str = "", feedback: str = "") -> Dict[str, Any]:
        if self._llm_fn is None:
            return self._default_investigation_step()

        history_text = [f"Step {h['step']}: {h['action_type']}" for h in self._history[-5:]]
        action_dict = self._llm_fn(observation, feedback, history_text)

        action_type = action_dict.get("action_type", "view_alerts")

        # Only allow safe actions during auto-investigation
        if action_type not in self._safe_actions:
            action_dict["action_type"] = "view_alerts"
            action_type = "view_alerts"

        result = self._scenario.handle_action(**action_dict)
        self._update_investigation_state(action_type, action_dict, result)

        step_record = {
            "step": len(self._history) + 1,
            "action_type": action_type,
            "action": action_dict,
            "reward": result.reward,
            "feedback": result.feedback,
            "auto": True,
        }
        self._history.append(step_record)

        return {
            "output": result.output,
            "feedback": result.feedback,
            "reward": result.reward,
            "done": result.done,
            "investigation_depth": self._investigation.investigation_depth,
        }

    def _default_investigation_step(self) -> Dict[str, Any]:
        """Default investigation strategy without LLM."""
        inv = self._investigation

        if not inv.alerts_reviewed:
            action = {"action_type": "view_alerts"}
        elif not inv.dependencies_checked:
            action = {"action_type": "check_dependencies"}
        elif len(inv.services_queried) < len(self._scenario.config.services):
            next_svc = [
                s for s in self._scenario.config.services
                if s not in inv.services_queried
            ]
            if next_svc:
                action = {"action_type": "query_logs", "service_name": next_svc[0]}
            else:
                action = {"action_type": "view_alerts"}
        else:
            uninspected = [
                s for s in self._scenario.config.services
                if s not in inv.diagnostics_run
            ]
            if uninspected:
                action = {"action_type": "run_diagnostic", "service_name": uninspected[0]}
            else:
                action = {"action_type": "view_alerts"}

        result = self._scenario.handle_action(**action)
        self._update_investigation_state(action["action_type"], action, result)

        self._history.append({
            "step": len(self._history) + 1,
            "action_type": action["action_type"],
            "action": action,
            "reward": result.reward,
            "feedback": result.feedback,
            "auto": True,
        })

        return {
            "output": result.output,
            "feedback": result.feedback,
            "reward": result.reward,
            "done": result.done,
            "investigation_depth": inv.investigation_depth,
        }

    def _update_investigation_state(
        self, action_type: str, action: Dict, result: Any
    ) -> None:
        """Update investigation tracking state."""
        inv = self._investigation

        if action_type == "view_alerts":
            inv.alerts_reviewed = True
            inv.investigation_depth = min(1.0, inv.investigation_depth + 0.1)
        elif action_type in ("query_logs", "query_metrics"):
            svc = action.get("service_name", "")
            if svc and svc not in inv.services_queried:
                inv.services_queried.append(svc)
                inv.investigation_depth = min(1.0, inv.investigation_depth + 0.15)
        elif action_type == "check_dependencies":
            inv.dependencies_checked = True
            inv.investigation_depth = min(1.0, inv.investigation_depth + 0.1)
        elif action_type == "run_diagnostic":
            svc = action.get("service_name", "")
            if svc and svc not in inv.diagnostics_run:
                inv.diagnostics_run.append(svc)
                inv.investigation_depth = min(1.0, inv.investigation_depth + 0.1)
        elif action_type == "classify_severity":
            inv.severity_classification = action.get("severity")

        # Extract findings from feedback
        if result.feedback and "finding" in result.feedback.lower():
            inv.findings.append(result.feedback)

    def propose_remediation(
        self,
        service_name: str,
        remediation: str,
        rationale: str,
        evidence: Optional[List[str]] = None,
    ) -> RemediationProposal:
        """Create a remediation proposal for human review."""
        self._proposal_counter += 1
        proposal_id = f"REM-{self._proposal_counter:04d}"

        risk_level, reversible = assess_risk("execute_remediation", remediation, service_name)

        # Count specificity keywords for confidence
        specificity = sum(1 for kw in [
            "deploy", "config", "rollback", "pool", "index", "cert",
            "dns", "memory", "rate limit", "connection",
        ] if kw in remediation.lower() or kw in rationale.lower())

        confidence = compute_confidence(self._investigation, specificity)

        proposal = RemediationProposal(
            proposal_id=proposal_id,
            action_type="execute_remediation",
            service_name=service_name,
            remediation=remediation,
            confidence=confidence,
            risk_level=risk_level,
            reversible=reversible,
            rationale=rationale,
            evidence=evidence or list(self._investigation.findings),
        )

        self._proposals[proposal_id] = proposal
        return proposal

    def review_proposal(
        self,
        proposal_id: str,
        status: ApprovalStatus,
        notes: str = "",
        modified_action: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Human reviews a proposal."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False

        proposal = RemediationProposal(
            proposal_id=proposal.proposal_id,
            action_type=proposal.action_type,
            service_name=proposal.service_name,
            remediation=proposal.remediation,
            confidence=proposal.confidence,
            risk_level=proposal.risk_level,
            reversible=proposal.reversible,
            rationale=proposal.rationale,
            evidence=proposal.evidence,
            status=status,
            reviewer_notes=notes,
            modified_action=modified_action,
            timestamp=proposal.timestamp,
        )
        self._proposals[proposal_id] = proposal
        return True

    def execute_approved(self, proposal_id: str) -> Dict[str, Any]:
        """Execute an approved remediation proposal."""
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status not in (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED):
            return {"error": f"Proposal {proposal_id} not approved"}

        # Use modified action if provided
        if proposal.status == ApprovalStatus.MODIFIED and proposal.modified_action:
            action = proposal.modified_action
        else:
            action = {
                "action_type": "execute_remediation",
                "service_name": proposal.service_name,
                "remediation": proposal.remediation,
            }

        result = self._scenario.handle_action(**action)

        self._history.append({
            "step": len(self._history) + 1,
            "action_type": action.get("action_type", "execute_remediation"),
            "action": action,
            "reward": result.reward,
            "feedback": result.feedback,
            "auto": False,
            "proposal_id": proposal_id,
            "approval_status": proposal.status.value,
        })

        return {
            "output": result.output,
            "feedback": result.feedback,
            "reward": result.reward,
            "done": result.done,
            "proposal_id": proposal_id,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the investigation and proposals."""
        return {
            "total_steps": len(self._history),
            "auto_steps": sum(1 for h in self._history if h.get("auto")),
            "manual_steps": sum(1 for h in self._history if not h.get("auto")),
            "investigation_depth": self._investigation.investigation_depth,
            "services_investigated": self._investigation.services_queried,
            "diagnostics_run": self._investigation.diagnostics_run,
            "findings": self._investigation.findings,
            "severity": self._investigation.severity_classification,
            "proposals": len(self._proposals),
            "pending": len(self.pending_proposals),
            "total_reward": self._scenario.total_reward,
            "score_breakdown": {
                "investigation": self._scenario.get_score_breakdown().investigation,
                "diagnosis": self._scenario.get_score_breakdown().diagnosis,
                "resolution": self._scenario.get_score_breakdown().resolution,
                "safety": self._scenario.get_score_breakdown().safety,
            },
        }
