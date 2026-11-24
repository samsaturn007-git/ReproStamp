import logging
import subprocess
import threading
from uuid import NAMESPACE_URL, uuid5

import psycopg

from ..control import store as runs
from ..control.database import connect
from ..control.settings import Settings
from ..repository import Repository, RepositoryError
from .client import GitHub, GitHubError
from .config import Pilot
from .store import PilotStore


log = logging.getLogger(__name__)
CONCLUSIONS = {
    "VERIFIED": "success", "FAILED": "failure",
    "INCONCLUSIVE": "action_required", "POLICY_BLOCKED": "action_required",
}
LOCAL_ERRORS = (OSError, RepositoryError, subprocess.SubprocessError)
RESPONSE_ERRORS = (GitHubError, KeyError, TypeError, ValueError)


def check_body(pilot: Pilot, row: dict, phase: str, *, prior_result: bool) -> dict:
    url = f"{pilot.dashboard_url}/?run={row['run_id']}"
    coverage = ", ".join(
        f"{engine} ({row['engine_verdicts'].get(engine, {}).get('name', 'awaiting verdict')})"
        for engine in row["plan"]["engines"]
    )
    summary = f"Base `{row['base_sha']}` · Candidate `{row['head_sha']}`\n\nBrowser coverage: {coverage}."
    body = {"details_url": url, "output": {"title": "", "summary": summary}}

    if phase == "superseded":
        body.update(status="completed", conclusion="neutral")
        body["output"].update(title="Evidence superseded", summary=(
            "The pull request moved away from the tested base and candidate.\n\n" + summary
        ))
    elif phase == "waiting":
        if prior_result:
            body.update(status="completed", conclusion="neutral")
        else:
            body["status"] = "in_progress"
        body["output"]["title"] = "Verification pending"
    else:
        verdict = row["verdict"]
        body.update(status="completed", conclusion=CONCLUSIONS.get(verdict, "action_required"))
        body["output"]["title"] = verdict or f"Run {row['state']}"
        body["output"]["summary"] = f"Reason: `{row['reason']}`.\n\n" + summary
    return body


class Integration:
    def __init__(self, settings: Settings, pilot: Pilot, github: GitHub):
        self.settings = settings
        self.pilot = pilot
        self.github = github
        self.repository = pilot.registered_repository(settings)
        self.state = PilotStore(settings, pilot)

    def ingest(self, delivery: dict) -> None:
        current = self.github.pull_refs(delivery["pr_number"])
        if current != (delivery["base_sha"], delivery["head_sha"]):
            self.state.discard_delivery(delivery, current)
            return
        base, head = current
        run_id = self.state.existing_run(delivery)
        if run_id is None:
            self.github.fetch_commits(Repository(self.repository.path), base, head)
            identity = f"reprostamp/github/{self.pilot.scope}/{delivery['id']}"
            run, _ = runs.submit(self.settings, uuid5(NAMESPACE_URL, identity), {
                "repo_id": self.repository.id, "profile_id": self.pilot.profile_id,
                "base_ref": base, "head_ref": head,
            })
            run_id = run["id"]
        self.state.queue_delivery(delivery, run_id)
        log.info("github_delivery_queued delivery=%s pr=%d run=%s head=%s",
                 delivery["id"], delivery["pr_number"], run_id, head)

    def publish(self, check: dict) -> None:
        head, external_id = check["head_sha"], str(check["external_id"])
        remote_id = check["remote_id"] or self.github.find_check(head, external_id)
        current = self.github.pull_refs(check["pr_number"])
        phase = check["phase"]
        if current != (check["base_sha"], head):
            self.state.supersede(check["pr_number"], current)
            phase = "superseded"

        body = check_body(self.pilot, check, phase, prior_result=(
            remote_id is not None and check["published_phase"] in ("final", "superseded")
        ))
        try:
            remote_id = self.github.publish(head, external_id, remote_id, body)
        except GitHubError as error:
            self.state.retry_check(check, missing_remote=error.status == 404)
            log.warning("github_publish_failed run=%s phase=%s error=%s", check["run_id"], phase, error)
            return
        self.state.published(check, remote_id, phase)
        metrics = self.state.metrics(check["run_id"])
        log.info("github_check_published run=%s check=%d phase=%s head=%s queue_ms=%s browser_ms=%d "
                 "worker_recoveries=%d publish_failures=%d", check["run_id"], remote_id, phase, head,
                 metrics["queue_ms"], metrics["browser_ms"], metrics["worker_recoveries"], check["publish_failures"])

    def tick(self) -> None:
        with connect(self.settings) as lock:
            lock.autocommit = True
            key = f"reprostamp/github/{self.pilot.scope}"
            acquired = lock.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired",
                                    (key,)).fetchone()["acquired"]
            if not acquired:
                return

            if delivery := self.state.next_delivery():
                try:
                    self.ingest(delivery)
                except (LOCAL_ERRORS + RESPONSE_ERRORS) as error:
                    self.state.retry_delivery(delivery)
                    log.warning("github_delivery_retry delivery=%s error=%s", delivery["id"], type(error).__name__)
            if check := self.state.next_check():
                try:
                    self.publish(check)
                except RESPONSE_ERRORS as error:
                    self.state.retry_check(check)
                    log.warning("github_publish_failed run=%s error=%s", check["run_id"], type(error).__name__)

    def work(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except psycopg.Error:
                log.exception("GitHub integration database operation failed and will be retried.")
            stop.wait(1)
