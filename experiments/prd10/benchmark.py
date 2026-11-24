"""Exercise the production PostgreSQL worker and the local Temporal prototype."""

import argparse
import asyncio
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.testing import WorkflowEnvironment

from reprostamp.control import store
from reprostamp.control.database import migrate
from reprostamp.control.inputs import freeze_inputs
from reprostamp.control.settings import ProfileRegistration, Registration, Settings
from reprostamp.control.worker import execution_id
from reprostamp.profile import load_profile
from reprostamp.receipt import browser_builds, matrix, verify_bundle
from reprostamp.runner import docker

from .workflow import LEASE_SECONDS, MAX_ATTEMPTS, Checkout, VerifyCheckout

ROOT = Path(__file__).resolve().parents[2]
CLI_VERSION = "1.8.3"
SDK_VERSION = "1.36.1"
REQUEST = {"repo_id": "checkout", "profile_id": "checkout",
           "base_ref": "checkout-base", "head_ref": "checkout-fixed"}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def elapsed(start: float, end: float) -> int:
    return round((end - start) * 1000)


async def until(check, description: str, seconds: int = 90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if result := check():
            return result
        await asyncio.sleep(0.15)
    raise RuntimeError(f"Timed out waiting for {description}.")


def stop(process: subprocess.Popen, *, crash: bool = False) -> None:
    if process.poll() is not None:
        if crash:
            raise RuntimeError("The worker exited before fault injection.")
        return
    if crash:
        process.kill()
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def worker(stack: ExitStack, trial: Path, name: str, *args: str, env: dict | None = None) -> subprocess.Popen:
    with (trial / f"{name}.log").open("wb") as output:
        process = subprocess.Popen([sys.executable, *args], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    stack.callback(stop, process)
    return process


def containers(run_id: UUID, attempt: int, *, running: bool) -> list[str]:
    label = f"label=io.reprostamp.run={execution_id(run_id, attempt)}"
    return docker("ps", "--filter", label, "--format", "{{.Names}}",
                  *([] if running else ["--all"]), timeout=10).split()


async def first_app(run_id: UUID, attempt: int) -> float:
    await until(lambda: any(name.endswith("-app") for name in containers(run_id, attempt, running=True)),
                f"generation {attempt} app container")
    return time.monotonic()


@contextmanager
def experiment_database(output: Path):
    password = (ROOT / ".reprostamp/prd03/postgres-password").read_text(encoding="ascii").strip()
    dsn = make_conninfo(host="127.0.0.1", hostaddr="127.0.0.1",
                        port=os.environ.get("REPROSTAMP_PG_PORT") or "55432", dbname="reprostamp",
                        user="reprostamp", password=password, connect_timeout=3)
    db_name = f"reprostamp_prd10_{uuid4().hex}"
    source = ROOT / "profiles/checkout.json"
    repo = ROOT / ".reprostamp/checkout/repo"
    approved = load_profile(source, repo)
    profile_path = output / "profile.json"
    write_json(profile_path, {"repository": repo, **asdict(replace(approved, engines=("chromium",)))})
    registration = Registration("checkout", "Checkout fixture", repo)
    profile = ProfileRegistration("checkout", "Chromium checkout", profile_path, registration.id,
                                  REQUEST["base_ref"], REQUEST["head_ref"])
    registry = output / "registry.json"
    write_json(registry, {"repositories": {registration.id: {"label": registration.label, "path": repo}},
                          "profiles": {profile.id: {**asdict(profile), "repo_id": profile.repo_id}}})
    settings = Settings(output / "postgres-data", make_conninfo(dsn, dbname=db_name),
                        "http://127.0.0.1:3000", {registration.id: registration}, {profile.id: profile}, LEASE_SECONDS)
    with psycopg.connect(dsn, autocommit=True) as admin:
        server_version = admin.execute("SHOW server_version").fetchone()[0]
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        try:
            migrate(settings)
            yield settings, registry, registration, profile, server_version
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name)))


def finish_trial(trial: Path, bundle: Path, run_id: UUID, attempt: int, digest: str, publications: int,
                 started: float, first: float, killed: float | None, retry: float | None, completed: float) -> dict:
    receipt = verify_bundle(bundle)
    payload = receipt["payload"]
    if (publications != 1 or receipt["payload_sha256"] != digest or payload["run_id"] != execution_id(run_id, attempt)
            or attempt != (2 if killed is not None else 1)):
        raise RuntimeError("The completed trial must accept exactly one receipt from the expected generation.")
    if payload["execution_state"] != "completed" or payload["verdict"] != "VERIFIED" or len(payload["attempts"]) != 4:
        raise RuntimeError(f"Unexpected comparison outcome for {bundle}.")
    if any(containers(run_id, number, running=False) for number in range(1, MAX_ATTEMPTS + 1)):
        raise RuntimeError(f"The runner left a container for {run_id}.")
    shutil.copyfile(bundle, trial / "receipt.zip")
    result = {
        "run_id": str(run_id), "worker_attempts": attempt, "accepted_receipts": publications,
        "submit_to_first_app_ms": elapsed(started, first), "wall_ms": elapsed(started, completed),
        "kill_to_retry_app_ms": elapsed(killed, retry) if killed is not None else None,
        "kill_to_result_ms": elapsed(killed, completed) if killed is not None else None,
        "execution_state": payload["execution_state"], "verdict": payload["verdict"],
        "receipt_sha256": digest, "receipt": str(trial / "receipt.zip"),
    }
    write_json(trial / "result.json", result)
    return result


async def postgres_trial(trial: Path, settings: Settings, registry: Path, crash: bool) -> dict:
    env = {**os.environ, "REPROSTAMP_DATA": str(settings.data), "REPROSTAMP_DATABASE_URL": settings.dsn,
           "REPROSTAMP_REGISTRY": str(registry)}
    key = uuid4()
    with ExitStack() as stack:
        original = worker(stack, trial, "first", "-m", "reprostamp.control", "worker", env=env)
        started = time.monotonic()
        row, _ = store.submit(settings, key, REQUEST)
        run_id = row["id"]
        first = await first_app(run_id, 1)
        killed = retry = None
        if crash:
            killed = time.monotonic()
            stop(original, crash=True)
            worker(stack, trial, "replacement", "-m", "reprostamp.control", "worker", env=env)
            retry = await first_app(run_id, 2)

        def terminal():
            current = store.get_run(settings, run_id)
            return current if current["state"] in store.TERMINAL else None

        row = await until(terminal, "PostgreSQL completion", seconds=140)
        completed = time.monotonic()
        duplicate, created = store.submit(settings, key, REQUEST)
        if created or duplicate["id"] != run_id:
            raise RuntimeError("A duplicate PostgreSQL submission started a second job.")
        events = store.events(settings, run_id, 0)[0]
        write_json(trial / "postgres-events.json", events)
        publications = sum(item["kind"] == "receipt" for item in row["artifacts"])
        if (sum(event["kind"] == "completed" for event in events) != 1
                or sum(event["kind"] == "lease_expired" for event in events) != int(crash)):
            raise RuntimeError("The PostgreSQL completion or recovery event count differs from the trial.")
        bundle = store.generation_path(settings, run_id, row["fence"]) / "evidence/receipt.zip"
        return finish_trial(trial, bundle, run_id, row["fence"], row["receipt_sha"], publications,
                            started, first, killed, retry, completed)


async def temporal_trial(trial: Path, client: Client, address: str, repo: Registration,
                         profile: ProfileRegistration, crash: bool) -> dict:
    run_id = uuid4()
    queue = f"reprostamp-prd10-{run_id}"
    args = ("-m", "experiments.prd10.worker", "worker", address, queue, str(trial), str(run_id))
    with ExitStack() as stack:
        original = worker(stack, trial, "first", *args)
        started = time.monotonic()
        base, head, _ = freeze_inputs(repo, profile, REQUEST["base_ref"], REQUEST["head_ref"], trial / "inputs")
        checkout = Checkout(str(run_id), base, head)

        async def submit():
            return await client.start_workflow(VerifyCheckout.run, checkout, id=str(run_id), task_queue=queue,
                                               id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)

        handle = await submit()
        first = await first_app(run_id, 1)
        killed = retry = None
        if crash:
            killed = time.monotonic()
            stop(original, crash=True)
            worker(stack, trial, "replacement", *args)
            retry = await first_app(run_id, 2)
        result = await asyncio.wait_for(handle.result(), timeout=140)
        completed = time.monotonic()
        try:
            await submit()
        except WorkflowAlreadyStartedError:
            pass
        else:
            raise RuntimeError("A duplicate Temporal submission started a second workflow.")
        history = await handle.fetch_history()
        (trial / "temporal-history.json").write_text(history.to_json() + "\n", encoding="utf-8")
        publications = sum(event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED for event in history.events)
        if sum(event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED for event in history.events) != 1:
            raise RuntimeError("Temporal must record exactly one completed workflow.")
        bundle = trial / f"work-{result.attempt}/evidence/receipt.zip"
        return finish_trial(trial, bundle, run_id, result.attempt, result.receipt_sha256, publications,
                            started, first, killed, retry, completed)


def semantics(receipt: Path) -> tuple:
    payload = verify_bundle(receipt)["payload"]
    comparison = tuple(payload[key] for key in ("base_sha", "head_sha", "inputs", "plan", "execution_state", "verdict", "reason"))
    cells = {key: (case["status"], case["assertion"], case["attempt_reason"]) for key, case in matrix(payload).items()}
    return comparison, browser_builds(payload), cells


async def benchmark(output: Path, cli: Path) -> None:
    version = subprocess.check_output([str(cli), "--version"], text=True, timeout=10).strip()
    if version.split()[:3] != ["temporal", "version", CLI_VERSION]:
        raise ValueError(f"Use Temporal CLI {CLI_VERSION}, got {version}.")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    rows = []
    with experiment_database(output) as (settings, registry, repo, profile, postgres_version):
        environment = await WorkflowEnvironment.start_local(
            port=port, dev_server_existing_path=str(cli), dev_server_log_level="error",
            dev_server_database_filename=str(output / "temporal.sqlite3"),
            dev_server_startup_timeout=timedelta(seconds=30),
        )
        async with environment:
            for scenario in ("control", "crash-1", "crash-2"):
                arms = ("temporal", "postgres") if scenario == "crash-1" else ("postgres", "temporal")
                for engine in arms:
                    trial = output / scenario / engine
                    trial.mkdir(parents=True)
                    crash = scenario != "control"
                    print(f"Running {scenario} with {engine}", flush=True)
                    if engine == "postgres":
                        result = await postgres_trial(trial, settings, registry, crash)
                    else:
                        result = await temporal_trial(trial, environment.client, f"127.0.0.1:{port}", repo, profile, crash)
                    rows.append({"scenario": scenario, "engine": engine, **result})
    expected = semantics(Path(rows[0]["receipt"]))
    if any(semantics(Path(row["receipt"])) != expected for row in rows[1:]):
        raise RuntimeError("The benchmark receipts disagree on controlled inputs or assertion outcomes.")
    write_json(output / "report.json", {
        "host": f"{platform.system()} {platform.machine()}",
        "postgresql": postgres_version, "temporal_cli": version, "temporal_sdk": SDK_VERSION,
        "lease_or_heartbeat_seconds": LEASE_SECONDS, "max_attempts": MAX_ATTEMPTS,
        "inputs": expected[0][2], "browser_builds": expected[1], "trials": rows,
    })
    print(f"Six equivalent receipts verified. Results saved in {output / 'report.json'}.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--temporal-cli", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    evidence_root = ROOT / ".reprostamp"
    if output == evidence_root or not output.is_relative_to(evidence_root):
        parser.error("Use a fresh evidence directory under .reprostamp.")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    asyncio.run(benchmark(output, args.temporal_cli.resolve(strict=True)))


if __name__ == "__main__":
    main()
