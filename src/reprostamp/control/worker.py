import argparse
import fcntl
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from uuid import UUID, uuid5

import psycopg

from ..cli import BUNDLE_ERRORS, ComparisonInterrupted, compare
from ..integrity import hash_file
from ..receipt import verify_bundle
from ..runner import Attempt, DockerError, docker
from . import store
from .database import connect
from .settings import Settings


log = logging.getLogger(__name__)


def execution_id(run_id: UUID, fence: int) -> str:
    return uuid5(run_id, str(fence)).hex


def execute_comparison(settings: Settings, run_id: UUID, fence: int) -> None:
    """Run the shared CLI comparison in a separately interruptible host process."""
    def check_lease() -> None:
        while True:
            try:
                with connect(settings) as db:
                    if store.lease(db, run_id, fence) != "running":
                        break
            except psycopg.Error:
                break
            time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)

    def interrupt(_number, _frame) -> None:
        raise ComparisonInterrupted()

    def record(engine: str, side: str, number: int, data: dict | None = None) -> None:
        if not store.observe(settings, run_id, fence, engine, side, number, data):
            raise ComparisonInterrupted()

    def record_finish(attempt: Attempt) -> None:
        record(attempt.engine, attempt.side, attempt.number, asdict(attempt))

    signal.signal(signal.SIGINT, interrupt)
    with connect(settings) as db:
        row = db.execute("SELECT base_sha, head_sha FROM runs WHERE id = %s AND fence = %s",
                         (run_id, fence)).fetchone()
    if row is None:
        return
    inputs = store.run_path(settings, run_id) / "inputs"
    folder = store.generation_path(settings, run_id, fence)
    try:
        threading.Thread(target=check_lease, daemon=True).start()
        compare(
            argparse.Namespace(repo=str(inputs / "repository"), profile=str(inputs / "profile.json"),
                               base=row["base_sha"], head=row["head_sha"], out=str(folder / "evidence")),
            run_id=execution_id(run_id, fence), workspace_parent=folder,
            on_attempt_start=record, on_attempt=record_finish,
        )
    except ComparisonInterrupted:
        pass


class Heartbeat:
    def __init__(self, settings: Settings, run_id: UUID, fence: int):
        self.settings = settings
        self.run_id = run_id
        self.fence = fence
        self.stop = threading.Event()
        self.state: str | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self.state = store.renew(self.settings, self.run_id, self.fence)
        self.thread.start()
        return self

    def __exit__(self, *_exception):
        self.stop.set()
        self.thread.join()

    def _run(self) -> None:
        while not self.stop.wait(0.75):
            try:
                self.state = store.renew(self.settings, self.run_id, self.fence)
            except psycopg.Error:
                log.exception("Lost database connection while renewing run %s", self.run_id)
                self.state = None
            if self.state is None:
                return


def cleanup_generation(folder, run_id: UUID, *, keep_evidence: bool = False) -> None:
    fence = int(folder.name.removeprefix("work-"))
    label = f"label=io.reprostamp.run={execution_id(run_id, fence)}"
    containers = docker("ps", "-aq", "--filter", label, timeout=5).split()
    for container in containers:
        try:
            docker("rm", "--force", container, timeout=5)
        except DockerError as error:
            if "No such container" not in str(error):
                raise
    if keep_evidence:
        for workspace in folder.glob(f"reprostamp-{execution_id(run_id, fence)}-*"):
            shutil.rmtree(workspace)
    else:
        shutil.rmtree(folder)


def verify_output(folder, row: dict) -> tuple[dict, list[dict]]:
    output = folder / "evidence"
    bundle = output / "receipt.zip"
    receipt = verify_bundle(bundle)
    payload = receipt["payload"]
    if payload["run_id"] != execution_id(row["id"], row["fence"]) or any(
        payload[f"{side}_sha"] != row[f"{side}_sha"] for side in ("base", "head")
    ):
        raise ValueError("The receipt does not match the leased comparison.")
    outcome = {
        "state": payload["execution_state"], "verdict": payload["verdict"], "reason": payload["reason"],
        "detail": payload["detail"], "receipt_sha": receipt["payload_sha256"],
        "engine_verdicts": payload["engine_verdicts"],
    }
    with bundle.open("rb") as source:
        bundle_hash = hash_file(source)
    approved = [{"kind": "receipt", "path": "receipt.zip", "size": bundle.stat().st_size, "sha256": bundle_hash}]
    kinds = {"trace.zip": "trace", "screenshot.png": "screenshot", "app.log": "log", "harness.log": "log",
             "receipt.md": "summary"}
    for path, metadata in payload["artifacts"].items():
        approved.append({"kind": kinds[path.rsplit("/", 1)[-1]], "path": path, **metadata})
    return outcome, approved


def run_child(lock, folder, heartbeat: Heartbeat, stopping: threading.Event) -> None:
    folder.mkdir(mode=0o700)
    with (folder / "worker.log").open("wb") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "reprostamp.control", "_execute", str(heartbeat.run_id), str(heartbeat.fence)],
            stdout=output, stderr=subprocess.STDOUT, pass_fds=(lock.fileno(),), start_new_session=True,
        )
        # Only the comparison process holds the execution lock while jobs run.
        # It releases the lock when its lease watchdog interrupts the workload.
        lock.close()
        while process.poll() is None and heartbeat.state == "running" and not stopping.wait(0.25):
            pass
        if process.poll() is None:
            try:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def process_run(settings: Settings, row: dict, stopping: threading.Event) -> None:
    run_id, fence = row["id"], row["fence"]
    root = store.run_path(settings, run_id)
    folder = store.generation_path(settings, run_id, fence)
    with Heartbeat(settings, run_id, fence) as heartbeat, (root / "execution.lock").open("ab") as lock:
        while heartbeat.state and not stopping.is_set():
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                stopping.wait(0.25)
        else:
            return

        state = store.renew(settings, run_id, fence)
        if state is None:
            return
        for old in sorted(root.glob("work-*")):
            cleanup_generation(old, run_id)
        if state == "running" and heartbeat.state == "running" and fence <= 2 and not stopping.is_set():
            run_child(lock, folder, heartbeat, stopping)
            if heartbeat.state is None:
                return
            cleanup_generation(folder, run_id, keep_evidence=True)

        if heartbeat.state is None or stopping.is_set():
            return
        state = store.renew(settings, run_id, fence)
        if state == "running":
            outcome, artifacts = {
                "state": "incomplete", "reason": "worker_lease_exhausted",
                "detail": "The worker lease expired during both executions.",
            }, []
            if folder.exists():
                try:
                    outcome, artifacts = verify_output(folder, row)
                except BUNDLE_ERRORS:
                    log.exception("Run %s generation %d did not produce an intact receipt", run_id, fence)
                    outcome = {"state": "incomplete", "reason": "worker_execution_failed",
                               "detail": "The worker did not produce an intact verification receipt."}
            if store.finalize(settings, run_id, fence, outcome, artifacts):
                return
            state = store.renew(settings, run_id, fence)
        if state == "cancelling":
            if folder.exists():
                cleanup_generation(folder, run_id)
            store.finalize(settings, run_id, fence, {
                "state": "cancelled", "reason": "owner_cancelled", "detail": "The run was cancelled and its workloads stopped.",
            }, [])


def work(settings: Settings) -> None:
    stopping = threading.Event()

    def stop(_number, _frame) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    next_sweep = 0.0
    while not stopping.is_set():
        try:
            if time.monotonic() >= next_sweep:
                store.purge_expired(settings)
                next_sweep = time.monotonic() + 5
            if row := store.claim(settings):
                log.info("Claimed run %s generation %d", row["id"], row["fence"])
                process_run(settings, row, stopping)
                continue
        except (psycopg.Error, OSError, DockerError, subprocess.TimeoutExpired):
            log.exception("Worker will resume polling after a temporary error")
        stopping.wait(0.5)
