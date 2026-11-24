from datetime import timedelta
from uuid import UUID, uuid4

from ..control import store as runs
from ..control.database import connect
from ..control.settings import Settings
from .config import Pilot


class PilotStore:
    def __init__(self, settings: Settings, pilot: Pilot):
        self.settings = settings
        self.scope = pilot.scope

    def receive(self, delivery: UUID, number: int, base: str, head: str) -> bool:
        with connect(self.settings) as db:
            return db.execute("""
                INSERT INTO github_deliveries
                    (id, installation_id, repository_id, profile_id, pr_number, base_sha, head_sha)
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """, (delivery, *self.scope, number, base, head)).rowcount == 1

    def next_delivery(self) -> dict | None:
        with connect(self.settings) as db:
            return db.execute("""
                SELECT * FROM github_deliveries
                WHERE (installation_id, repository_id, profile_id) = (%s, %s, %s)
                    AND state = 'pending' AND retry_at <= clock_timestamp()
                ORDER BY received_at, id LIMIT 1
            """, self.scope).fetchone()

    def existing_run(self, delivery: dict) -> UUID | None:
        with connect(self.settings) as db:
            row = db.execute("""
                SELECT c.run_id FROM github_checks c JOIN runs r ON r.id = c.run_id
                WHERE (c.installation_id, c.repository_id, c.profile_id) = (%s, %s, %s)
                    AND c.pr_number = %s AND c.base_sha = %s AND c.head_sha = %s AND NOT c.superseded
                    AND (r.expires_at IS NULL OR r.expires_at > clock_timestamp())
            """, (*self.scope, delivery["pr_number"], delivery["base_sha"], delivery["head_sha"])).fetchone()
            return row["run_id"] if row else None

    def queue_delivery(self, delivery: dict, run_id: UUID) -> None:
        number, base, head = delivery["pr_number"], delivery["base_sha"], delivery["head_sha"]
        with connect(self.settings) as db:
            self._mark_previous(db, number, (base, head))
            previous = db.execute("""
                SELECT run_id FROM github_checks
                WHERE (installation_id, repository_id, profile_id, head_sha) = (%s, %s, %s, %s) FOR UPDATE
            """, (*self.scope, head)).fetchone()
            if previous and previous["run_id"] != run_id:
                self._mark_evidence(db, previous["run_id"])
            db.execute("""
                INSERT INTO github_checks
                    (installation_id, repository_id, profile_id, head_sha, external_id, pr_number, base_sha, run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (installation_id, repository_id, profile_id, head_sha) DO UPDATE SET
                    pr_number = EXCLUDED.pr_number, base_sha = EXCLUDED.base_sha, run_id = EXCLUDED.run_id,
                    superseded = false, retry_at = clock_timestamp()
                WHERE github_checks.run_id <> EXCLUDED.run_id OR github_checks.superseded
            """, (*self.scope, head, uuid4(), number, base, run_id))
            db.execute("UPDATE github_deliveries SET state = 'queued', run_id = %s WHERE id = %s",
                       (run_id, delivery["id"]))

    def discard_delivery(self, delivery: dict, current: tuple[str, str] | None) -> None:
        with connect(self.settings) as db:
            self._mark_previous(db, delivery["pr_number"], current)
            db.execute("UPDATE github_deliveries SET state = 'superseded' WHERE id = %s", (delivery["id"],))

    @staticmethod
    def _mark_evidence(db, run_id: UUID) -> None:
        if db.execute("UPDATE runs SET superseded_at = clock_timestamp() WHERE id = %s AND superseded_at IS NULL",
                      (run_id,)).rowcount:
            runs.event(db, run_id, "superseded", reason="github_pr_refs_changed")

    def _mark_previous(self, db, number: int, current: tuple[str, str] | None) -> None:
        base, head = current or (None, None)
        changed = db.execute("""
            UPDATE github_checks SET superseded = true, retry_at = clock_timestamp()
            WHERE (installation_id, repository_id, profile_id) = (%s, %s, %s)
                AND pr_number = %s AND NOT superseded AND (base_sha, head_sha) IS DISTINCT FROM (%s, %s)
            RETURNING run_id
        """, (*self.scope, number, base, head)).fetchall()
        for row in changed:
            self._mark_evidence(db, row["run_id"])

    def supersede(self, number: int, current: tuple[str, str] | None) -> None:
        with connect(self.settings) as db:
            self._mark_previous(db, number, current)

    def next_check(self) -> dict | None:
        with connect(self.settings) as db:
            return db.execute("""
                WITH desired AS (
                    SELECT c.*, r.state, r.verdict, r.reason, r.plan, r.engine_verdicts, r.created_at,
                        CASE WHEN c.superseded THEN 'superseded'
                             WHEN r.finished_at IS NOT NULL THEN 'final'
                             ELSE 'waiting' END AS phase
                    FROM github_checks c JOIN runs r ON r.id = c.run_id
                    WHERE (c.installation_id, c.repository_id, c.profile_id) = (%s, %s, %s)
                        AND c.retry_at <= clock_timestamp()
                )
                SELECT * FROM desired
                WHERE published_run_id IS DISTINCT FROM run_id OR published_phase IS DISTINCT FROM phase
                ORDER BY (phase = 'waiting'), retry_at, created_at, external_id LIMIT 1
            """, self.scope).fetchone()

    def published(self, check: dict, remote_id: int, phase: str) -> None:
        with connect(self.settings) as db:
            db.execute("""
                UPDATE github_checks SET remote_id = %s, published_run_id = %s, published_phase = %s,
                    retry_at = clock_timestamp() WHERE external_id = %s AND run_id = %s
            """, (remote_id, check["run_id"], phase, check["external_id"], check["run_id"]))

    def retry_delivery(self, delivery: dict) -> None:
        delay = timedelta(seconds=min(300, 2 ** min(9, delivery["failures"] + 1)))
        with connect(self.settings) as db:
            db.execute("""
                UPDATE github_deliveries SET failures = failures + 1, retry_at = clock_timestamp() + %s WHERE id = %s
            """, (delay, delivery["id"]))

    def retry_check(self, check: dict, *, missing_remote: bool = False) -> None:
        delay = timedelta(seconds=min(300, 5 * 2 ** min(6, check["publish_failures"])))
        with connect(self.settings) as db:
            db.execute("""
                UPDATE github_checks SET publish_failures = publish_failures + 1,
                    retry_at = clock_timestamp() + %s, remote_id = CASE WHEN %s THEN NULL ELSE remote_id END
                WHERE external_id = %s AND run_id = %s
            """, (delay, missing_remote, check["external_id"], check["run_id"]))

    def metrics(self, run_id: UUID) -> dict:
        with connect(self.settings) as db:
            return db.execute("""
                SELECT
                    (SELECT round(1000 * extract(epoch FROM (min(created_at) - r.created_at)))::bigint
                     FROM run_events WHERE run_id = r.id AND kind = 'started') AS queue_ms,
                    (SELECT coalesce(sum((result->>'duration_ms')::bigint), 0)::bigint
                     FROM attempts WHERE run_id = r.id) AS browser_ms,
                    (SELECT count(*) FROM run_events WHERE run_id = r.id AND kind = 'retry_started')
                        AS worker_recoveries
                FROM runs r WHERE r.id = %s
            """, (run_id,)).fetchone()
