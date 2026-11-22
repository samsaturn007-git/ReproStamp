"""Exercise the dashboard, durable runs, worker fencing, and owner access on a fresh database."""

import concurrent.futures
import hashlib
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from reprostamp.control import store
from reprostamp.control.database import connect, migrate
from reprostamp.control.settings import Settings
from reprostamp.control.worker import execution_id
from reprostamp.receipt import verify_bundle


ROOT = Path(__file__).resolve().parents[1]
CONTROL = [sys.executable, "-m", "reprostamp.control"]


def available_port():
    with socket.socket() as listening:
        listening.bind(("127.0.0.1", 0))
        return listening.getsockname()[1]


def until(predicate, *, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if result := predicate():
            return result
        time.sleep(0.15)
    raise AssertionError(f"Condition did not pass within {seconds}s: {predicate}")


def call(opener, origin, path, *, body=None, headers=None, method=None, code=200):
    request = urllib.request.Request(
        origin + "/api/v1" + path, None if body is None else json.dumps(body).encode(),
        {"Content-Type": "application/json", **(headers or {})}, method=method,
    )
    try:
        response = opener.open(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        assert response.code in (code if isinstance(code, tuple) else (code,)), (request.full_url, response.code, data[:2000])
        if response.headers.get_content_type() == "application/json":
            data = json.loads(data)
        return data, response.headers


def start(stack, output, name, environment, arguments):
    with (output / f"{name}.log").open("wb") as log:
        process = subprocess.Popen(arguments, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    stack.callback(stop, process)
    return process


def stop(process, kill=False):
    if process.poll() is not None:
        return
    import signal

    os.killpg(process.pid, signal.SIGKILL if kill else signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def listening(origin, path):
    try:
        with urllib.request.urlopen(origin + path, timeout=3) as response:
            return response.status == 200
    except OSError:
        return False


def git(*arguments):
    return subprocess.check_output(["git", *arguments], text=True, timeout=30).strip()


def prepare_registry(output):
    source_profile = ROOT / "profiles/checkout.json"
    data = json.loads(source_profile.read_text())
    repo = output / "registered-repo"
    harness = output / "registered-harness"
    git("clone", "--quiet", "--no-local", str((source_profile.parent / data["repository"]).resolve()), str(repo))
    shutil.copytree((source_profile.parent / data["harness"]).resolve(), harness,
                    ignore=shutil.ignore_patterns("node_modules", ".DS_Store"))
    data.update(repository=str(repo), harness=str(harness),
                npm_cache=str((source_profile.parent / data["npm_cache"]).resolve()))
    profile = output / "registered-profile.json"
    profile.write_text(json.dumps(data))
    registry = output / "registry.json"
    registry.write_text(json.dumps({
        "repositories": {"checkout": {"label": "Discount checkout", "path": str(repo)}},
        "profiles": {"checkout": {"label": "Three-browser verification", "path": str(profile), "repo_id": "checkout",
                                  "base": "checkout-base", "head": "checkout-fixed"}},
    }))
    return registry, repo, harness


def containers(run_id, fence, *, running=False):
    return subprocess.check_output(["docker", "ps", "-q" if running else "-aq", "--filter",
                                    f"label=io.reprostamp.run={execution_id(run_id, fence)}"], text=True, timeout=10).split()


def exercise(stack, output, settings, registry, repo, harness, api_port):
    with connect(settings) as db:
        assert db.execute("SELECT to_regclass('runs') AS runs").fetchone()["runs"] is None
    migrate(settings)
    migrate(settings)
    with connect(settings) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"] == "0001_durable_runs"
    print("PASS empty PostgreSQL database migrated, with repeat migration a no-op", flush=True)

    environment = {
        **os.environ, "REPROSTAMP_ORIGIN": settings.origin, "REPROSTAMP_API_PORT": str(api_port),
        "REPROSTAMP_DATA": str(settings.data), "REPROSTAMP_DATABASE_URL": settings.dsn, "REPROSTAMP_REGISTRY": str(registry),
    }
    dashboard_port = settings.origin.rsplit(":", 1)[1]
    api_origin = f"http://127.0.0.1:{api_port}"
    start_api = lambda selected: start(stack, output, selected, environment, [*CONTROL, "serve", "--port", str(api_port)])
    api_process = start_api("api")
    until(lambda: listening(api_origin, "/api/v1/openapi.json"))
    dashboard = ["npm", "--prefix", "dashboard", "run", "dev", "--", "--port", dashboard_port]
    start(stack, output, "dashboard", environment, dashboard)
    until(lambda: listening(settings.origin, "/"), seconds=60)

    anon = urllib.request.build_opener()
    owner = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    same_origin = {"Origin": settings.origin}
    password = settings.owner_password()
    call(owner, api_origin, "/session", body={"password": password}, headers={"Origin": "http://other.invalid"}, code=403)
    session, response_headers = call(owner, api_origin, "/session", body={"password": password}, headers=same_origin)
    assert "HttpOnly" in response_headers["Set-Cookie"] and "SameSite=strict" in response_headers["Set-Cookie"]
    write = {**same_origin, "X-CSRF-Token": session["csrf_token"]}
    body = {"repo_id": "checkout", "profile_id": "checkout", "base_ref": "checkout-base", "head_ref": "checkout-fixed"}
    headers = {**write, "Idempotency-Key": str(uuid.uuid4())}
    call(anon, api_origin, "/runs", code=401)
    call(owner, api_origin, "/runs", body=body, headers={**headers, "Origin": "http://other.invalid"}, code=403)
    call(owner, api_origin, "/runs", body=body, headers={**headers, "X-CSRF-Token": "wrong"}, code=403)
    call(owner, api_origin, "/runs", body={**body, "repo_id": "unknown"}, headers=headers, code=404)
    call(owner, api_origin, "/runs", body={**body, "repository": str(repo)}, headers=headers, code=422)

    # Start the first transaction and use the same idempotency key from another request concurrently.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda _: call(owner, api_origin, "/runs", body=body, headers=headers,
                                           code=(200, 201))[0], range(2)))
    assert rows[0]["id"] == rows[1]["id"]
    call(owner, api_origin, "/runs", body={**body, "head_ref": "checkout-base"}, headers=headers, code=409)
    queued = rows[0]["id"]
    cancelled, _ = call(owner, api_origin, f"/runs/{queued}/cancel", headers=write, method="POST")
    assert cancelled["state"] == "cancelled" and cancelled["verdict"] is None
    timeline, _ = call(owner, api_origin, f"/runs/{queued}/timeline")
    assert [event["kind"] for event in timeline["events"]] == ["queued", "cancelled"]
    print("PASS owner session, origin/CSRF checks, registry IDs, concurrent duplicate and queued cancellation", flush=True)

    worker = start(stack, output, "worker", environment, [*CONTROL, "worker"])
    browser = start(stack, output, "browser", environment, [
        "node", "tests/prd03_browser.cjs", settings.origin, str(output), str(settings.data / "owner-password"),
    ])
    marker = output / "browser-run-id"
    until(marker.exists, seconds=60)
    run_id = uuid.UUID(marker.read_text())
    until(lambda: containers(run_id, 1, running=True))
    stop(worker, kill=True)
    stop(api_process, kill=True)
    until((output / "browser-disconnected").exists)

    tag = git("-C", str(repo), "rev-parse", "checkout-fixed")
    base = git("-C", str(repo), "rev-parse", "checkout-base")
    git("-C", str(repo), "update-ref", "refs/tags/checkout-fixed", base)
    spec = harness / "checkout.spec.cjs"
    original_spec = spec.read_bytes()
    spec.unlink()
    start_api("api-restarted")
    until(lambda: listening(api_origin, "/api/v1/openapi.json"))
    replacement = start(stack, output, "worker-replacement", environment, [*CONTROL, "worker"])

    def current():
        return store.get_run(settings, run_id)

    until(lambda: current()["fence"] == 2 and current()["state"] == "running")
    assert not store.finalize(settings, run_id, 1, {
        "state": "completed", "verdict": "VERIFIED", "reason": "stale", "detail": "Outdated completion",
    }, [])
    assert not store.observe(settings, run_id, 1, "webkit", "head", 2, None)
    until((output / "browser-recovered").exists, seconds=170)
    finished = current()
    assert finished["state"] == "completed" and finished["verdict"] == "VERIFIED" and finished["head_sha"] == tag
    assert finished["receipt_sha"] and finished["fence"] == 2
    assert abs(finished["expires_at"] - finished["finished_at"] - timedelta(days=30)) < timedelta(seconds=1)
    assert len([attempt for attempt in finished["attempts"] if attempt["fence"] == 2]) == 12
    assert any(attempt["fence"] == 1 and attempt["state"] == "interrupted" for attempt in finished["attempts"])
    assert sum(item["kind"] == "receipt" for item in finished["artifacts"]) == 1
    assert not containers(run_id, 1) and not containers(run_id, 2)
    assert not store.generation_path(settings, run_id, 1).exists()
    receipt = verify_bundle(output / "ui-receipt.zip")
    assert receipt["payload_sha256"] == finished["receipt_sha"] and receipt["payload"]["head_sha"] == tag
    assert zipfile.is_zipfile(output / "ui-trace.zip")
    recovered = json.loads((output / "browser-timeline.json").read_text())
    cursor = int(next(cursor for cursor in recovered["cursors"] if int(cursor or "0") >= 3))
    timeline, _ = call(owner, api_origin, f"/runs/{run_id}/timeline?after={cursor}")
    assert [event["seq"] for event in timeline["events"]] == [seq for seq in recovered["sequences"] if seq > cursor]
    assert sum(event["kind"] == "completed" for event in timeline["events"]) == 1
    receipt_path = f"/runs/{run_id}/receipt"
    trace = next(item for item in finished["artifacts"] if item["kind"] == "trace")
    trace_path = f"/runs/{run_id}/artifacts/{trace['id']}"
    call(anon, api_origin, receipt_path, code=401)
    call(anon, api_origin, trace_path, code=401)
    call(anon, api_origin, f"/runs/{run_id}/events", code=401)
    trace_data, trace_headers = call(owner, api_origin, trace_path)
    assert trace_headers.get_content_type() == "application/zip"
    assert trace_headers["Content-Disposition"].startswith("attachment;")
    assert hashlib.sha256(trace_data).hexdigest() == trace["sha256"]
    print("PASS killed worker recovered frozen refs and harness, stale writes fenced, one intact receipt and protected trace", flush=True)

    git("-C", str(repo), "update-ref", "refs/tags/checkout-fixed", tag)
    spec.write_bytes(original_spec)
    running, _ = call(owner, api_origin, "/runs", body=body, headers={**write, "Idempotency-Key": str(uuid.uuid4())}, code=201)
    cancelled_id = uuid.UUID(running["id"])
    until(lambda: containers(cancelled_id, 1, running=True))
    call(owner, api_origin, f"/runs/{cancelled_id}/cancel", headers=write, method="POST")

    def cancelled():
        row = store.get_run(settings, cancelled_id)
        return row if row["state"] == "cancelled" else None

    outcome = until(cancelled)
    assert outcome["verdict"] is None and not outcome["artifacts"] and not containers(cancelled_id, 1)
    cancelled_events, _ = call(owner, api_origin, f"/runs/{cancelled_id}/timeline")
    assert [event["kind"] for event in cancelled_events["events"]][-2:] == ["cancelling", "cancelled"]
    print("PASS cancellation stopped an active workload and persisted cancelled with no verdict", flush=True)

    twice, _ = call(owner, api_origin, "/runs", body=body, headers={**write, "Idempotency-Key": str(uuid.uuid4())}, code=201)
    exhausted_id = uuid.UUID(twice["id"])
    until(lambda: containers(exhausted_id, 1, running=True))
    stop(replacement, kill=True)
    second_worker = start(stack, output, "worker-second-retry", environment, [*CONTROL, "worker"])
    until(lambda: containers(exhausted_id, 2, running=True))
    stop(second_worker, kill=True)
    start(stack, output, "worker-final", environment, [*CONTROL, "worker"])

    def exhausted():
        row = store.get_run(settings, exhausted_id)
        return row if row["state"] == "incomplete" else None

    outcome = until(exhausted)
    assert outcome["reason"] == "worker_lease_exhausted" and outcome["verdict"] is None
    assert not outcome["artifacts"] and not containers(exhausted_id, 1) and not containers(exhausted_id, 2)
    print("PASS two worker losses exhausted the single recovery retry without publishing a receipt", flush=True)

    with connect(settings) as db:
        db.execute("UPDATE runs SET expires_at = clock_timestamp() - interval '1 second' WHERE id = %s", (run_id,))
    call(owner, api_origin, receipt_path, code=410)
    call(owner, api_origin, trace_path, code=410)
    (output / "evidence-expired").touch()
    until(lambda: not store.run_path(settings, run_id).exists())
    assert browser.wait(timeout=40) == 0, (output / "browser.log").read_text()
    print((output / "browser.log").read_text(), end="")
    print("PASS expired downloads return 410 and the worker purged files", flush=True)


def main():
    local = Settings.local()
    output = Path(tempfile.mkdtemp(prefix="prd03-gates-", dir=ROOT / ".reprostamp"))
    print(f"Evidence directory: {output}", flush=True)
    registry, repo, harness = prepare_registry(output)
    database = f"reprostamp_gate_{uuid.uuid4().hex}"
    api_port, dashboard_port = available_port(), available_port()
    while api_port == dashboard_port:
        dashboard_port = available_port()
    settings = replace(local, data=output / "data", dsn=make_conninfo(local.dsn, dbname=database),
                       origin=f"http://127.0.0.1:{dashboard_port}")
    with psycopg.connect(local.dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            with ExitStack() as stack:
                exercise(stack, output, settings, registry, repo, harness, api_port)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    print(f"PRD-03 exit gates passed. Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
