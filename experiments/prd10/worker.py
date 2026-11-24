"""Opt-in Temporal worker for the registered local experiment."""

import argparse
import asyncio
import fcntl
import os
import signal
import sys
import threading
import time
from pathlib import Path
from uuid import UUID

from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from reprostamp.cli import ComparisonInterrupted, compare
from reprostamp.control.worker import cleanup_generation, execution_id, verify_output
from reprostamp.repository import Repository

from .workflow import Checkout, Completion, VerifyCheckout

MODULE = "experiments.prd10.worker"


def compare_child(root: Path, run_id: UUID, attempt: int, parent: int) -> int:
    def watch_parent() -> None:
        while os.getppid() == parent:
            time.sleep(0.15)
        os.kill(os.getpid(), signal.SIGINT)

    def interrupt(_signum, _frame) -> None:
        raise ComparisonInterrupted()

    signal.signal(signal.SIGINT, interrupt)
    inputs = root / "inputs"
    folder = root / f"work-{attempt}"
    try:
        threading.Thread(target=watch_parent, daemon=True).start()
        return compare(argparse.Namespace(
            repo=str(inputs / "repository"), profile=str(inputs / "profile.json"),
            base="refs/reprostamp/base", head="refs/reprostamp/head", out=str(folder / "evidence"),
        ), run_id=execution_id(run_id, attempt), workspace_parent=folder)
    except ComparisonInterrupted:
        return 3


async def run_comparison(root: Path, folder: Path, lock, run_id: UUID, attempt: int) -> None:
    with (folder / "worker.log").open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", MODULE, "child", str(root), str(run_id), str(attempt), str(os.getpid()),
            stdout=log, stderr=asyncio.subprocess.STDOUT, pass_fds=(lock.fileno(),),
        )
        # The child inherits this lock and releases it after cleaning up the runner.
        lock.close()
        try:
            while process.returncode is None:
                activity.heartbeat()
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.5)
                except TimeoutError:
                    continue
        finally:
            if process.returncode is None:
                process.send_signal(signal.SIGINT)
                try:
                    await asyncio.wait_for(process.wait(), timeout=15)
                except TimeoutError:
                    process.kill()
                    await process.wait()


class CheckoutActivities:
    def __init__(self, root: Path, run_id: UUID):
        self.root = root
        self.run_id = run_id

    @activity.defn
    async def compare_checkout(self, checkout: Checkout) -> Completion:
        if checkout.run_id != str(self.run_id) or checkout.run_id != activity.info().workflow_id:
            raise ApplicationError("This worker serves only its registered checkout job.", non_retryable=True)
        repo = Repository(self.root / "inputs/repository")
        refs = ("refs/reprostamp/base", "refs/reprostamp/head")
        if tuple(repo.resolve(ref) for ref in refs) != (checkout.base_sha, checkout.head_sha):
            raise ApplicationError("The commits do not match the frozen checkout.", non_retryable=True)
        attempt = activity.info().attempt
        with (self.root / "execution.lock").open("ab") as lock:
            while True:
                activity.heartbeat()
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.15)
            for previous in self.root.glob("work-*"):
                cleanup_generation(previous, self.run_id)
            folder = self.root / f"work-{attempt}"
            folder.mkdir(mode=0o700)
            await run_comparison(self.root, folder, lock, self.run_id, attempt)
        outcome, _ = verify_output(folder, {"id": self.run_id, "fence": attempt,
                                           "base_sha": checkout.base_sha, "head_sha": checkout.head_sha})
        return Completion(attempt, outcome["state"], outcome["verdict"], outcome["receipt_sha"])


async def serve(address: str, queue: str, root: Path, run_id: UUID) -> None:
    client = await Client.connect(address)
    activities = CheckoutActivities(root, run_id)
    async with Worker(client, task_queue=queue, workflows=[VerifyCheckout], activities=[activities.compare_checkout]):
        print("Temporal checkout worker ready", flush=True)
        await asyncio.Event().wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("address")
    worker.add_argument("queue")
    worker.add_argument("root", type=Path)
    worker.add_argument("run_id", type=UUID)
    child = commands.add_parser("child")
    child.add_argument("root", type=Path)
    child.add_argument("run_id", type=UUID)
    child.add_argument("attempt", type=int)
    child.add_argument("parent", type=int)
    args = parser.parse_args()
    if args.command == "child":
        return compare_child(args.root, args.run_id, args.attempt, args.parent)
    asyncio.run(serve(args.address, args.queue, args.root, args.run_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
