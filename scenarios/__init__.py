from .base import BaseScenario
from .alert_triage import AlertTriageScenario
from .root_cause_analysis import RootCauseAnalysisScenario
from .cascading_failure import CascadingFailureScenario
from .ticket_triage import TicketTriageScenario

SCENARIOS = {
    "alert_triage": AlertTriageScenario,
    "root_cause_analysis": RootCauseAnalysisScenario,
    "cascading_failure": CascadingFailureScenario,
    "ticket_triage": TicketTriageScenario,
}

__all__ = [
    "BaseScenario",
    "AlertTriageScenario",
    "RootCauseAnalysisScenario",
    "CascadingFailureScenario",
    "TicketTriageScenario",
    "SCENARIOS",
]
