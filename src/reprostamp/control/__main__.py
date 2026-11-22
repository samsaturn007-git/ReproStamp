import argparse
import json
import logging
from pathlib import Path
from uuid import UUID

from .api import create_app
from .database import migrate
from .settings import Settings
from .worker import execute_comparison, work


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m reprostamp.control")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply the local PostgreSQL schema")
    server = commands.add_parser("serve", help="start the loopback API")
    server.add_argument("--port", type=int, default=8000)
    commands.add_parser("worker", help="claim and work approved comparison runs")
    contract = commands.add_parser("openapi", help="write the OpenAPI contract")
    contract.add_argument("output", type=Path)
    child = commands.add_parser("_execute")
    child.add_argument("id", type=UUID)
    child.add_argument("fence", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "openapi":
        args.output.write_text(json.dumps(create_app(describe=True).openapi(), indent=2) + "\n", encoding="utf-8")
        return
    settings = Settings.local()
    if args.command == "migrate":
        migrate(settings)
        settings.owner_password()
    elif args.command == "serve":
        import uvicorn

        uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port)
    elif args.command == "worker":
        work(settings)
    else:
        execute_comparison(settings, args.id, args.fence)


if __name__ == "__main__":
    main()
