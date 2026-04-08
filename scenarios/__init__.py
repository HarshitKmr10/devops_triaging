from .base import BaseScenario
from .alert_triage import AlertTriageScenario
from .root_cause_analysis import RootCauseAnalysisScenario
from .cascading_failure import CascadingFailureScenario

SCENARIOS = {
    "alert_triage": AlertTriageScenario,
    "root_cause_analysis": RootCauseAnalysisScenario,
    "cascading_failure": CascadingFailureScenario,
}

__all__ = [
    "BaseScenario",
    "AlertTriageScenario",
    "RootCauseAnalysisScenario",
    "CascadingFailureScenario",
    "SCENARIOS",
]
