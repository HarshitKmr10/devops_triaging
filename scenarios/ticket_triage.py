"""
Task 4: IT Service Ticket Triage (Medium)

The agent acts as an ITSM service desk analyst processing incoming support tickets.
Must:
1. Review the ticket queue
2. Classify each ticket by category (hardware, software, network, access, change_request)
3. Assign priority (P1-P4) based on business impact
4. Route to the correct resolver group
5. Handle an urgent VIP escalation mid-triage

Scenario: A batch of 6 tickets arrive simultaneously. One is a VIP CEO escalation
hiding among routine requests. The agent must identify it, reprioritize, and handle
the SLA-critical items first.
"""

from typing import Optional

from .base import ActionResult, BaseScenario, ScenarioConfig


# ─── Ticket Data ──────────────────────────────────────────────────────────

_TICKETS = {
    "TKT-4001": {
        "subject": "Cannot access Salesforce - login loop",
        "requester": "Sarah Chen (Sales Director)",
        "submitted": "2024-03-15T09:00:00Z",
        "description": (
            "Since this morning I'm stuck in a login loop when trying to access Salesforce. "
            "I've cleared cookies, tried incognito mode, and restarted my laptop. "
            "Quarterly sales review is at 2 PM today and I need my pipeline data. "
            "3 other sales reps on my team are also affected."
        ),
        "category": "access",
        "priority": "P2",
        "resolver_group": "identity-team",
        "sla_hours": 4,
        "impact": "4 users, revenue-critical meeting today",
    },
    "TKT-4002": {
        "subject": "Printer on 3rd floor not working",
        "requester": "Mike Johnson (Marketing Intern)",
        "submitted": "2024-03-15T09:05:00Z",
        "description": (
            "The HP printer near the kitchen on 3rd floor is showing 'Paper Jam' "
            "but there's no paper stuck that I can see. Can someone take a look?"
        ),
        "category": "hardware",
        "priority": "P4",
        "resolver_group": "facilities-team",
        "sla_hours": 48,
        "impact": "1 user, non-critical",
    },
    "TKT-4003": {
        "subject": "URGENT: CEO cannot access board presentation",
        "requester": "James Wright (Executive Assistant to CEO)",
        "submitted": "2024-03-15T09:02:00Z",
        "description": (
            "CEO Robert Martinez CANNOT open the Q1 board presentation on SharePoint. "
            "Getting 'Access Denied' error. The board meeting is in 90 MINUTES. "
            "This is the CEO's #1 priority right now. Please treat as HIGHEST URGENCY. "
            "File path: /sites/executive/Q1-Board-Deck-Final.pptx"
        ),
        "category": "access",
        "priority": "P1",
        "resolver_group": "identity-team",
        "sla_hours": 1,
        "impact": "CEO, board meeting in 90 minutes, executive visibility",
        "vip": True,
    },
    "TKT-4004": {
        "subject": "Request to install Docker Desktop",
        "requester": "Priya Patel (Junior Developer)",
        "submitted": "2024-03-15T09:10:00Z",
        "description": (
            "I need Docker Desktop installed on my workstation for the new microservices project. "
            "My manager (Tom Lee) has approved it. Software request form SR-2024-0892 attached."
        ),
        "category": "change_request",
        "priority": "P3",
        "resolver_group": "desktop-engineering",
        "sla_hours": 24,
        "impact": "1 user, approved change request",
    },
    "TKT-4005": {
        "subject": "VPN disconnecting every 10 minutes",
        "requester": "David Park (Remote Engineer)",
        "submitted": "2024-03-15T09:08:00Z",
        "description": (
            "GlobalProtect VPN keeps dropping every 10 minutes since the update last night. "
            "I'm remote today and can't maintain SSH sessions to production servers. "
            "I've checked my home internet and it's stable. Other remote workers in #vpn-issues "
            "Slack channel are reporting the same problem (at least 15 people)."
        ),
        "category": "network",
        "priority": "P2",
        "resolver_group": "network-team",
        "sla_hours": 4,
        "impact": "15+ remote workers, productivity impact",
    },
    "TKT-4006": {
        "subject": "Laptop running slow after Windows update",
        "requester": "Lisa Wang (HR Coordinator)",
        "submitted": "2024-03-15T09:15:00Z",
        "description": (
            "My laptop has been really slow since the Windows update yesterday. "
            "Takes 5 minutes to open Outlook. Not urgent but annoying."
        ),
        "category": "software",
        "priority": "P4",
        "resolver_group": "desktop-engineering",
        "sla_hours": 48,
        "impact": "1 user, degraded performance",
    },
}

_RESOLVER_GROUPS = {
    "identity-team": "Handles SSO, MFA, access provisioning, SharePoint permissions",
    "network-team": "Handles VPN, firewall, DNS, network connectivity issues",
    "desktop-engineering": "Handles software installs, OS issues, hardware replacement",
    "facilities-team": "Handles printers, physical equipment, office infrastructure",
    "security-team": "Handles security incidents, phishing, compromised accounts",
    "database-team": "Handles database access, query issues, backup/restore",
}

_SCENARIO_SERVICES = (
    "ticket-queue", "identity-team", "network-team",
    "desktop-engineering", "facilities-team",
)

# Grading: correct classification and prioritization
_CORRECT_TRIAGE = {
    "TKT-4003": {"priority": "P1", "category": "access", "resolver": "identity-team"},  # CEO - must be first
    "TKT-4001": {"priority": "P2", "category": "access", "resolver": "identity-team"},
    "TKT-4005": {"priority": "P2", "category": "network", "resolver": "network-team"},
    "TKT-4004": {"priority": "P3", "category": "change_request", "resolver": "desktop-engineering"},
    "TKT-4002": {"priority": "P4", "category": "hardware", "resolver": "facilities-team"},
    "TKT-4006": {"priority": "P4", "category": "software", "resolver": "desktop-engineering"},
}


def _format_ticket_queue() -> str:
    """Format the ticket queue as a service desk view."""
    lines = [
        "=" * 70,
        "  IT SERVICE DESK - INCOMING TICKET QUEUE",
        "=" * 70,
        f"  Tickets waiting: {len(_TICKETS)}  |  SLA breaches imminent: 2",
        "=" * 70, "",
    ]
    for tid, t in _TICKETS.items():
        vip_tag = " [VIP]" if t.get("vip") else ""
        lines.append(f"  {tid}{vip_tag}: {t['subject']}")
        lines.append(f"    From: {t['requester']}  |  Submitted: {t['submitted']}")
        lines.append(f"    SLA: {t['sla_hours']}h  |  Impact: {t['impact']}")
        lines.append("")
    return "\n".join(lines)


def _format_ticket_detail(ticket_id: str) -> str:
    """Format a single ticket in detail."""
    t = _TICKETS.get(ticket_id)
    if not t:
        return f"Ticket '{ticket_id}' not found. Available: {', '.join(_TICKETS.keys())}"
    vip_tag = " [VIP ESCALATION]" if t.get("vip") else ""
    return (
        f"Ticket: {ticket_id}{vip_tag}\n"
        f"  Subject: {t['subject']}\n"
        f"  Requester: {t['requester']}\n"
        f"  Submitted: {t['submitted']}\n"
        f"  Description: {t['description']}\n"
        f"  SLA Target: {t['sla_hours']} hours\n"
        f"  Impact: {t['impact']}"
    )


def _format_resolver_groups() -> str:
    lines = ["=" * 50, "  RESOLVER GROUPS", "=" * 50, ""]
    for name, desc in _RESOLVER_GROUPS.items():
        lines.append(f"  {name}: {desc}")
    return "\n".join(lines)


class TicketTriageScenario(BaseScenario):
    """Medium scenario: ITSM ticket triage with VIP escalation."""

    def __init__(self) -> None:
        super().__init__()
        self._tickets_triaged: dict[str, dict] = {}
        self._vip_identified: bool = False
        self._correct_count: int = 0

    @property
    def config(self) -> ScenarioConfig:
        return ScenarioConfig(
            task_id="ticket_triage",
            task_name="IT Service Ticket Triage",
            difficulty="medium",
            description=(
                "You are an IT Service Desk analyst. A batch of 6 support tickets has arrived. "
                "Your job is to: (1) Review the ticket queue, (2) Read each ticket's details, "
                "(3) Classify each by category and priority (P1-P4), and (4) Route to the correct "
                "resolver group. IMPORTANT: One ticket is a VIP escalation with a critical SLA - "
                "identify and handle it first. Use view_alerts to see the queue, query_logs to "
                "read ticket details, inspect_service to view resolver groups, classify_severity "
                "to set priority, and escalate to route tickets."
            ),
            max_steps=25,
            services=_SCENARIO_SERVICES,
            system_status="ACTIVE - 6 tickets in queue. 2 SLA breaches imminent.",
            noise_services=(),
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

        # Danger zone
        danger = self._check_danger_zone(action_type, command=command, remediation=remediation)
        if danger:
            feedback = f"DANGER: {danger}. Safety score reduced."
            reward = -0.05
            reward = self._clamp_reward(reward)
            self._record_step(action_type, reward, service_name)
            return ActionResult(output="", reward=reward, feedback=feedback)

        if action_type == "view_alerts":
            output = _format_ticket_queue()
            if self._achieve_milestone("viewed_queue"):
                reward = 0.05
                self._investigation_score += 0.15
                self._mark_investigated()
                feedback = (
                    "Ticket queue loaded. Notice TKT-4003 is a VIP escalation with only 90 min "
                    "until the board meeting. Prioritize it."
                )
            else:
                feedback = "Queue already reviewed."

        elif action_type == "query_logs":
            # Use service_name as ticket_id, or keyword
            ticket_id = service_name or keyword or ""
            ticket_id = ticket_id.upper().strip()
            if ticket_id in _TICKETS:
                output = _format_ticket_detail(ticket_id)
                if self._achieve_milestone(f"read_{ticket_id}"):
                    reward = 0.02
                    self._investigation_score += 0.1
                    self._mark_investigated()
                    if _TICKETS[ticket_id].get("vip") and self._achieve_milestone("vip_noticed"):
                        self._vip_identified = True
                        reward += 0.05
                        feedback = (
                            "VIP ESCALATION detected! CEO cannot access board presentation. "
                            "Board meeting in 90 minutes. Handle this FIRST."
                        )
                    else:
                        feedback = f"Ticket {ticket_id} details retrieved."
                else:
                    feedback = f"Already read {ticket_id}."
            else:
                output = f"Ticket '{ticket_id}' not found.\nAvailable tickets: {', '.join(_TICKETS.keys())}"
                feedback = "Use the ticket ID (e.g., TKT-4003) as service_name to read details."

        elif action_type == "inspect_service":
            if service_name == "ticket-queue":
                output = _format_ticket_queue()
                feedback = "Ticket queue displayed."
            else:
                output = _format_resolver_groups()
                if self._achieve_milestone("viewed_resolvers"):
                    reward = 0.03
                    self._investigation_score += 0.1
                    feedback = "Resolver groups listed. Match tickets to the right team."
                else:
                    feedback = "Resolver groups already reviewed."

        elif action_type == "check_dependencies":
            output = _format_resolver_groups()
            if self._achieve_milestone("viewed_resolvers_dep"):
                reward = 0.02
                feedback = "Resolver groups displayed."
            else:
                feedback = "Already viewed."

        elif action_type == "classify_severity":
            # Classify a specific ticket: use service_name=ticket_id, severity=P1-P4
            ticket_id = (service_name or "").upper().strip()
            if ticket_id in _CORRECT_TRIAGE and severity:
                expected = _CORRECT_TRIAGE[ticket_id]
                sev = severity.upper().strip()
                if sev == expected["priority"]:
                    if self._achieve_milestone(f"priority_{ticket_id}"):
                        reward = 0.05
                        self._diagnosis_score += 0.15
                        # Extra reward for correctly prioritizing VIP first
                        if ticket_id == "TKT-4003" and self._step_count <= 5:
                            reward += 0.05
                            feedback = f"Correct! {ticket_id} is {sev}. Good - you prioritized the VIP early."
                        else:
                            feedback = f"Correct! {ticket_id} classified as {sev}."
                    else:
                        feedback = f"{ticket_id} already classified."
                else:
                    if self._achieve_milestone(f"priority_attempt_{ticket_id}"):
                        reward = 0.01
                    feedback = f"Incorrect. {ticket_id} should be {expected['priority']} based on impact: {_TICKETS[ticket_id]['impact']}"
            elif ticket_id:
                feedback = f"Ticket '{ticket_id}' not recognized. Use ticket IDs like TKT-4003."
            else:
                feedback = "Provide service_name=<ticket_id> and severity=<P1-P4>."

        elif action_type == "escalate":
            # Route ticket to resolver: service_name=ticket_id, team=resolver_group
            ticket_id = (service_name or "").upper().strip()
            resolver = (team or "").lower().strip()
            if ticket_id in _CORRECT_TRIAGE and resolver:
                expected = _CORRECT_TRIAGE[ticket_id]
                if resolver == expected["resolver"]:
                    if self._achieve_milestone(f"routed_{ticket_id}"):
                        reward = 0.05
                        self._resolution_score += 0.16
                        self._correct_count += 1
                        self._tickets_triaged[ticket_id] = {"resolver": resolver, "correct": True}
                        feedback = f"Correct! {ticket_id} routed to {resolver}."
                        # Check if all tickets triaged
                        if self._correct_count >= 6:
                            self._done = True
                            reward += 0.05
                            feedback += " All tickets triaged! Excellent work."
                    else:
                        feedback = f"{ticket_id} already routed."
                else:
                    if self._achieve_milestone(f"route_attempt_{ticket_id}"):
                        reward = 0.01
                    self._tickets_triaged[ticket_id] = {"resolver": resolver, "correct": False}
                    feedback = f"Wrong team. {ticket_id} ({_TICKETS[ticket_id]['category']}) should go to {expected['resolver']}, not {resolver}."
            else:
                feedback = "Provide service_name=<ticket_id> and team=<resolver_group>."

        elif action_type == "identify_root_cause":
            feedback = "This is a triage task. Use classify_severity and escalate to process tickets."
            reward = 0.0

        elif action_type == "execute_remediation":
            feedback = "This is a triage task. Route tickets to resolver groups using escalate."
            reward = 0.0

        elif action_type in ("query_metrics", "run_diagnostic"):
            output = "No metrics/diagnostics available for service desk tickets. Read tickets with query_logs."
            feedback = "Use query_logs with service_name=<ticket_id> to read ticket details."

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
