import gradio as gr

from models import IncidentAction, VALID_ACTION_TYPES
from scenarios import SCENARIOS
from server.environment import IncidentResponseEnvironment

# Global environment instance for the UI session
_env = IncidentResponseEnvironment()
_history: list[dict] = []


def reset_environment(task_id: str) -> tuple[str, str, str, str]:
    """Reset environment and return initial observation."""
    global _history
    _history = []

    obs = _env.reset(task_id=task_id)
    state = _env.state

    status_text = (
        f"**Task:** {obs.task_id} ({obs.difficulty})\n"
        f"**System Status:** {obs.system_status}\n"
        f"**Max Steps:** {obs.max_steps}"
    )

    history_md = "_Episode started. Begin your investigation._"

    return obs.output, status_text, "0.00", history_md


def take_action(
    action_type: str,
    service_name: str,
    keyword: str,
    severity: str,
    root_cause: str,
    remediation: str,
    team: str,
) -> tuple[str, str, str, str]:
    """Execute an action and return updated observation."""
    global _history

    action_kwargs = {"action_type": action_type}
    if service_name:
        action_kwargs["service_name"] = service_name
    if keyword:
        action_kwargs["keyword"] = keyword
    if severity:
        action_kwargs["severity"] = severity
    if root_cause:
        action_kwargs["root_cause"] = root_cause
    if remediation:
        action_kwargs["remediation"] = remediation
    if team:
        action_kwargs["team"] = team

    try:
        action = IncidentAction(**action_kwargs)
        obs = _env.step(action)
    except Exception as e:
        return f"Error: {e}", "", "0.00", ""

    state = _env.state

    # Build reward display
    reward_text = obs.reward or 0.0
    total_reward = state.total_reward

    status_text = (
        f"**Task:** {state.task_id} ({state.difficulty})\n"
        f"**System Status:** {obs.system_status}\n"
        f"**Step:** {state.step}/{state.max_steps}\n"
        f"**Step Reward:** {reward_text:.2f}\n"
        f"**Total Reward:** {total_reward:.3f}\n"
        f"**Done:** {'YES' if obs.done else 'No'}"
    )

    # Add to history
    entry = {
        "step": state.step,
        "action": action_type,
        "service": service_name or "-",
        "reward": f"{reward_text:.2f}",
        "feedback": obs.feedback,
    }
    _history.append(entry)

    # Format history
    history_lines = []
    for h in _history:
        icon = "+" if float(h["reward"]) > 0 else ("-" if float(h["reward"]) < 0 else " ")
        history_lines.append(
            f"**Step {h['step']}** [{icon}{h['reward']}] `{h['action']}` "
            f"({h['service']})\n> {h['feedback']}"
        )
    history_md = "\n\n".join(history_lines)

    total_display = f"{total_reward:.3f}"

    # Output
    output = obs.output
    if obs.feedback and not output:
        output = obs.feedback
    if obs.done:
        resolved = "RESOLVED" if total_reward >= 0.6 else "UNRESOLVED"
        output += f"\n\n{'='*50}\nEPISODE COMPLETE - {resolved}\nFinal Score: {total_reward:.3f}\n{'='*50}"

    return output, status_text, total_display, history_md


def build_ui() -> gr.Blocks:
    """Build the Gradio web interface."""
    with gr.Blocks(
        title="ITSM Intelligence Environment",
    ) as app:
        gr.Markdown(
            "# ITSM Intelligence Environment\n"
            "Investigate production incidents and triage IT service tickets like a real SRE. "
            "Query alerts, logs, metrics, classify tickets, and execute remediations."
        )

        with gr.Row():
            with gr.Column(scale=1):
                task_dropdown = gr.Dropdown(
                    choices=list(SCENARIOS.keys()),
                    value="alert_triage",
                    label="Select Task",
                )
                reset_btn = gr.Button("Reset / Start New Episode", variant="primary")

                gr.Markdown("### Action Controls")
                action_type = gr.Dropdown(
                    choices=VALID_ACTION_TYPES,
                    value="view_alerts",
                    label="Action Type",
                )
                service_name = gr.Textbox(label="Service Name", placeholder="e.g., payment-service")
                keyword = gr.Textbox(label="Keyword (for log search)", placeholder="e.g., error, timeout")
                severity = gr.Textbox(label="Severity (P1-P4)", placeholder="e.g., P1")
                root_cause = gr.Textbox(label="Root Cause", placeholder="Describe the root cause...")
                remediation = gr.Textbox(label="Remediation", placeholder="Describe the fix...")
                team = gr.Textbox(label="Team", placeholder="e.g., payments-team")
                action_btn = gr.Button("Execute Action", variant="secondary")

            with gr.Column(scale=2):
                with gr.Row():
                    status_display = gr.Markdown(value="_Select a task and click Reset to begin._", label="Status")
                    total_reward_display = gr.Textbox(value="0.00", label="Total Reward", interactive=False)

                output_display = gr.Textbox(
                    value="",
                    label="Environment Output",
                    lines=18,
                    interactive=False,
                )

                gr.Markdown("### Action History & Feedback")
                history_display = gr.Markdown(value="_No actions taken yet._")

        # Wire up events
        reset_btn.click(
            fn=reset_environment,
            inputs=[task_dropdown],
            outputs=[output_display, status_display, total_reward_display, history_display],
        )

        action_btn.click(
            fn=take_action,
            inputs=[action_type, service_name, keyword, severity, root_cause, remediation, team],
            outputs=[output_display, status_display, total_reward_display, history_display],
        )

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
