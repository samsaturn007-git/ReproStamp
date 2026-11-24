#!/usr/bin/env python3
"""Provision and check the dashboard and PostgreSQL stack."""

import argparse
import hashlib
import os
import secrets
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
PASSWORD_FILE = ROOT / ".reprostamp/prd03/postgres-password"
RELEASE_LOCK = ROOT / "requirements/hosted-release.lock"


def run(*command: str, timeout: int = 180) -> None:
    subprocess.run(command, cwd=ROOT, check=True, timeout=timeout)


def database_password() -> str:
    PASSWORD_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not PASSWORD_FILE.exists():
        with tempfile.NamedTemporaryFile(dir=PASSWORD_FILE.parent, mode="w", encoding="ascii") as staged:
            staged.write(secrets.token_hex(32) + "\n")
            staged.flush()
            try:
                os.link(staged.name, PASSWORD_FILE)
            except FileExistsError:
                pass
    return PASSWORD_FILE.read_text(encoding="ascii").strip()


def check_database(port: int, password: str) -> None:
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import URL, create_engine

    url = URL.create("postgresql+psycopg", username="reprostamp", password=password,
                     host="127.0.0.1", port=port, database="reprostamp")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            pg_version = connection.exec_driver_sql("SHOW server_version").scalar_one()
            revisions = MigrationContext.configure(connection).get_current_heads()
    finally:
        engine.dispose()
    print(f"PostgreSQL {pg_version} at 127.0.0.1:{port}", flush=True)
    print(f"Alembic revisions: {', '.join(revisions) if revisions else 'none'}", flush=True)


def check_dashboard() -> None:
    run(sys.executable, "-m", "reprostamp.control", "openapi", str(PASSWORD_FILE.parent / "openapi.json"))
    run("npm", "--prefix", str(DASHBOARD), "run", "generate")
    run("npm", "--prefix", str(DASHBOARD), "run", "typecheck")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stop", action="store_true", help="stop PostgreSQL and preserve its data")
    mode.add_argument("--release", action="store_true", help="install the release package and locked dependencies")
    args = parser.parse_args()
    project = "reprostamp-prd03-" + hashlib.sha256(os.fsencode(ROOT)).hexdigest()[:12]
    compose = ("docker", "compose", "--progress", "quiet", "--project-name", project,
               "--env-file", os.devnull, "--file", str(ROOT / "compose.prd03.yml"))
    if args.stop:
        run(*compose, "stop", "postgres")
        return

    requested_port = os.environ.get("REPROSTAMP_PG_PORT") or "55432"
    if (not requested_port.isascii() or not requested_port.isdecimal() or len(requested_port) > 5
        or not 1 <= int(requested_port) <= 65535):
        parser.error("REPROSTAMP_PG_PORT must be an integer between 1 and 65535.")
    node = subprocess.check_output(["node", "-p", "process.versions.node"], text=True, timeout=10)
    if tuple(map(int, node.strip().split("."))) < (22, 12, 0):
        parser.error("Node.js 22.12 or newer is required.")
    run("docker", "compose", "version")
    install = (sys.executable, "-m", "pip", "install", "--disable-pip-version-check")
    if args.release:
        run(*install, "--only-binary=:all:", "-r", str(RELEASE_LOCK))
        run(*install, "--no-build-isolation", "--constraint", str(RELEASE_LOCK), ".[prd03]")
        run(sys.executable, "-m", "pip", "check")
    else:
        run(*install, "-e", ".[prd03]")
    run("npm", "--prefix", str(DASHBOARD), "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--include=dev")

    password = database_password()
    run(*compose, "up", "--wait", "--wait-timeout", "60", "postgres", timeout=240)
    check_database(int(requested_port), password)
    for name in ("fastapi", "pydantic", "uvicorn", "SQLAlchemy", "psycopg", "alembic"):
        print(f"{name} {version(name)}", flush=True)
    check_dashboard()


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError) as error:
        sys.exit(f"PRD-03 setup: {error}")
