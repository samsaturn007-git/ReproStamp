import argparse
import logging
import os
from pathlib import Path

import uvicorn

from ..control.settings import Settings
from .client import GitHub
from .config import Pilot
from .integration import Integration
from .webhook import webhook_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve GitHub webhooks and publish pilot check runs.")
    parser.add_argument("--config", type=Path, default=os.environ.get("REPROSTAMP_GITHUB_CONFIG"), required=(
        not os.environ.get("REPROSTAMP_GITHUB_CONFIG")
    ), help="owner-managed GitHub App configuration file")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pilot = Pilot.from_file(args.config.resolve(strict=True))
    uvicorn.run(webhook_app(Integration(Settings.local(), pilot, GitHub(pilot))), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
