"""
FastAPI application for the DevOps Incident Response Environment.

Exposes the IncidentResponseEnvironment over HTTP and WebSocket
endpoints, compatible with OpenEnv EnvClient.

Endpoints:
    - POST /reset: Reset the environment
    - POST /step: Execute an action
    - GET /state: Get current environment state
    - GET /health: Health check
    - WS /ws: WebSocket endpoint for persistent sessions

Usage:
    uvicorn server.app:app --host 0.0.0.0 --port 8000
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:
    raise ImportError(
        "openenv is required. Install with: pip install openenv-core[core]>=0.2.2"
    ) from e

try:
    from ..models import IncidentAction, IncidentObservation
    from .environment import IncidentResponseEnvironment
except (ModuleNotFoundError, ImportError):
    from models import IncidentAction, IncidentObservation
    from server.environment import IncidentResponseEnvironment


app = create_app(
    IncidentResponseEnvironment,
    IncidentAction,
    IncidentObservation,
    env_name="devops_incident_response",
    max_concurrent_envs=10,
)


def main() -> None:
    """Entry point for direct execution."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="DevOps Incident Response Environment Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
