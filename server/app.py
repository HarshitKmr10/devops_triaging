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
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="DevOps Incident Response Environment Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
