import hashlib
import secrets
import shutil
from datetime import timedelta
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .database import connect
from .inputs import freeze_inputs
from .settings import Settings


TERMINAL = frozenset(("completed", "incomplete", "blocked", "cancelled"))
RETENTION_DAYS = 30
RUN_FIELDS = "*, expires_at <= clock_timestamp() AS expired"


class SubmissionConflict(ValueError):
    pass


def run_path(settings: Settings, run_id: UUID):
    return settings.data / "runs" / str(run_id)


def generation_path(settings: Settings, run_id: UUID, fence: int):
    return run_path(settings, run_id) / f"work-{fence}"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(settings: Settings) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with connect(settings) as db:
        db.execute("DELETE FROM owner_sessions WHERE expires_at <= clock_timestamp()")
        db.execute("INSERT INTO owner_sessions VALUES (%s, %s, clock_timestamp() + interval '12 hours')",
                   (token_hash(token), csrf))
    return token, csrf


def session(settings: Settings, token: str | None) -> str | None:
    if not token:
        return None
    with connect(settings) as db:
        row = db.execute("""
            SELECT csrf_token FROM owner_sessions WHERE token_hash = %s AND expires_at > clock_timestamp()
        """, (token_hash(token),)).fetchone()
    return row["csrf_token"] if row else None


def delete_session(settings: Settings, token: str) -> None:
    with connect(settings) as db:
        db.execute("DELETE FROM owner_sessions WHERE token_hash = %s", (token_hash(token),))


def event(db, run_id: UUID, kind: str, **data) -> None:
    row = db.execute("UPDATE runs SET event_seq = event_seq + 1 WHERE id = %s RETURNING event_seq",
                     (run_id,)).fetchone()
    db.execute("INSERT INTO run_events (run_id, seq, kind, data) VALUES (%s, %s, %s, %s)",
               (run_id, row["event_seq"], kind, Jsonb(data)))


def submit(settings: Settings, key: UUID, request: dict) -> tuple[dict, bool]:
    with connect(settings) as db:
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(key),))
        existing = db.execute(f"SELECT {RUN_FIELDS} FROM runs WHERE submission_key = %s", (key,)).fetchone()
        if existing:
            if existing["request"] != request:
                raise SubmissionConflict("This submission key belongs to a different run request.")
            return existing, False
        registration = settings.profiles[request["profile_id"]]
        repository = settings.repositories[request["repo_id"]]
        run_id = uuid4()
        folder = run_path(settings, run_id)
        try:
            base, head, plan = freeze_inputs(repository, registration, request["base_ref"], request["head_ref"],
                                             folder / "inputs")
            row = db.execute(f"""
                INSERT INTO runs (id, submission_key, request, base_sha, head_sha, plan, state)
                VALUES (%s, %s, %s, %s, %s, %s, 'queued') RETURNING {RUN_FIELDS}
            """, (run_id, key, Jsonb(request), base, head, Jsonb(plan))).fetchone()
            event(db, run_id, "queued", state="queued")
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return row, True


def get_run(settings: Settings, run_id: UUID) -> dict | None:
    with connect(settings) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        row = db.execute(f"SELECT {RUN_FIELDS} FROM runs WHERE id = %s", (run_id,)).fetchone()
        if row is None:
            return None
        row["attempts"] = db.execute("""
            SELECT fence, engine, side, number, state, result FROM attempts
            WHERE run_id = %s ORDER BY fence, engine, side, number
        """, (run_id,)).fetchall()
        row["artifacts"] = db.execute("""
            SELECT id, kind, path, size, sha256 FROM artifacts
            WHERE run_id = %s AND kind <> 'summary' ORDER BY path
        """, (run_id,)).fetchall()
        return row


def runs(settings: Settings) -> list[dict]:
    with connect(settings) as db:
        return db.execute(f"SELECT {RUN_FIELDS} FROM runs ORDER BY created_at DESC, id DESC LIMIT 100").fetchall()


def events(settings: Settings, run_id: UUID, after: int) -> tuple[list[dict], bool]:
    with connect(settings) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        row = db.execute("SELECT state, event_seq FROM runs WHERE id = %s", (run_id,)).fetchone()
        batch = db.execute("""
            SELECT seq, kind, data, created_at FROM run_events
            WHERE run_id = %s AND seq > %s ORDER BY seq LIMIT 100
        """, (run_id, after)).fetchall()
        terminal = row["state"] in TERMINAL and (batch[-1]["seq"] if batch else after) >= row["event_seq"]
        return batch, terminal


def artifact(settings: Settings, run_id: UUID, artifact_id: UUID | None) -> dict | None:
    with connect(settings) as db:
        clause = "a.kind = 'receipt'" if artifact_id is None else "a.id = %s AND a.kind <> 'summary'"
        args = (run_id,) if artifact_id is None else (run_id, artifact_id)
        return db.execute(f"""
            SELECT a.*, runs.fence, runs.expires_at <= clock_timestamp() AS expired
            FROM artifacts a JOIN runs ON runs.id = a.run_id WHERE a.run_id = %s AND {clause}
        """, args).fetchone()


def cancel(settings: Settings, run_id: UUID) -> dict | None:
    with connect(settings) as db:
        row = db.execute("SELECT state FROM runs WHERE id = %s FOR UPDATE", (run_id,)).fetchone()
        if row is None:
            return None
        if row["state"] == "queued":
            finish(db, run_id, "cancelled", reason="owner_cancelled", detail="Cancelled before execution.")
        elif row["state"] == "running":
            db.execute("UPDATE runs SET state = 'cancelling' WHERE id = %s", (run_id,))
            event(db, run_id, "cancelling", state="cancelling")
        return db.execute(f"SELECT {RUN_FIELDS} FROM runs WHERE id = %s", (run_id,)).fetchone()


def claim(settings: Settings) -> dict | None:
    with connect(settings) as db:
        row = db.execute("""
            SELECT id, state, fence, base_sha, head_sha FROM runs
            WHERE state = 'queued' OR (state IN ('running', 'cancelling') AND lease_until <= clock_timestamp())
            ORDER BY (state = 'queued'), created_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
        """).fetchone()
        if row is None:
            return None
        run_id = row["id"]
        previous = row["state"]
        row["fence"] += 1
        row["state"] = "cancelling" if previous == "cancelling" else "running"
        db.execute("""
            UPDATE runs SET state = %s, fence = %s, lease_until = clock_timestamp() + %s WHERE id = %s
        """, (row["state"], row["fence"], timedelta(seconds=settings.lease_seconds), run_id))
        if previous != "queued":
            interrupt(db, run_id)
            event(db, run_id, "lease_expired", state=row["state"], generation=row["fence"] - 1)
        if row["state"] == "running" and row["fence"] <= 2:
            event(db, run_id, "started" if row["fence"] == 1 else "retry_started",
                  state="running", generation=row["fence"])
        return row


def lease(db, run_id: UUID, fence: int, *, lock: bool = False) -> str | None:
    row = db.execute("""
        SELECT state, lease_until > clock_timestamp() AS active FROM runs
        WHERE id = %s AND fence = %s
    """ + (" FOR UPDATE" if lock else ""), (run_id, fence)).fetchone()
    if row and row["state"] in ("running", "cancelling") and row["active"]:
        return row["state"]
    return None


def renew(settings: Settings, run_id: UUID, fence: int) -> str | None:
    with connect(settings) as db:
        state = lease(db, run_id, fence, lock=True)
        if state:
            db.execute("UPDATE runs SET lease_until = clock_timestamp() + %s WHERE id = %s",
                       (timedelta(seconds=settings.lease_seconds), run_id))
        return state


def observe(settings: Settings, run_id: UUID, fence: int, engine: str, side: str, number: int,
            data: dict | None) -> bool:
    with connect(settings) as db:
        if lease(db, run_id, fence, lock=True) != "running":
            return False
        state = data["status"] if data else "running"
        db.execute("""
            INSERT INTO attempts (run_id, fence, engine, side, number, state, result)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, fence, engine, side, number)
            DO UPDATE SET state = EXCLUDED.state, result = EXCLUDED.result
        """, (run_id, fence, engine, side, number, state, Jsonb(data) if data else None))
        event(db, run_id, f"attempt_{'finished' if data else 'started'}",
              generation=fence, engine=engine, side=side, number=number, status=state)
    return True


def interrupt(db, run_id: UUID) -> None:
    db.execute("UPDATE attempts SET state = 'interrupted' WHERE run_id = %s AND state = 'running'", (run_id,))


def finish(db, run_id: UUID, state: str, *, verdict: str | None = None, reason: str,
           detail: str, receipt_sha: str | None = None, engine_verdicts: dict | None = None) -> None:
    interrupt(db, run_id)
    db.execute("""
        UPDATE runs SET state = %s, verdict = %s, reason = %s, detail = %s, receipt_sha = %s,
          engine_verdicts = %s, finished_at = clock_timestamp(),
          expires_at = clock_timestamp() + %s, lease_until = NULL WHERE id = %s
    """, (state, verdict, reason, detail, receipt_sha, Jsonb(engine_verdicts or {}),
          timedelta(days=RETENTION_DAYS), run_id))
    event(db, run_id, state, state=state, verdict=verdict, reason=reason)


def finalize(settings: Settings, run_id: UUID, fence: int, outcome: dict, approved: list[dict]) -> bool:
    with connect(settings) as db:
        expected = "cancelling" if outcome["state"] == "cancelled" else "running"
        if lease(db, run_id, fence, lock=True) != expected:
            return False
        for item in approved:
            db.execute("""
                INSERT INTO artifacts (id, run_id, kind, path, size, sha256) VALUES (%s, %s, %s, %s, %s, %s)
            """, (uuid4(), run_id, item["kind"], item["path"], item["size"], item["sha256"]))
        finish(db, run_id, **outcome)
    return True


def purge_expired(settings: Settings) -> None:
    with connect(settings) as db:
        for row in db.execute("""
            SELECT id FROM runs WHERE expires_at <= clock_timestamp() AND purged_at IS NULL
            ORDER BY expires_at LIMIT 16 FOR UPDATE SKIP LOCKED
        """).fetchall():
            folder = run_path(settings, row["id"])
            if folder.exists():
                shutil.rmtree(folder)
            db.execute("UPDATE runs SET purged_at = clock_timestamp() WHERE id = %s", (row["id"],))
