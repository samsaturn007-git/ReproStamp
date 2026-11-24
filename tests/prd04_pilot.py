"""Run the PRD-04 integration against a local GitHub HTTP test server and real browser workloads."""

import hashlib
import hmac
import json
import logging
import os
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
from contextlib import ExitStack
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psycopg
import uvicorn
from psycopg import sql
from psycopg.conninfo import make_conninfo

from prd03_exit_gate import CONTROL, available_port, containers, git, prepare_registry, start, stop, until
from reprostamp.control.database import connect, migrate
from reprostamp.control.settings import Settings
from reprostamp.control.store import generation_path, get_run
from reprostamp.github.client import API_VERSION, CHECK_NAME, GitHub
from reprostamp.github.config import Pilot
from reprostamp.github.integration import Integration
from reprostamp.github.webhook import webhook_app
from reprostamp.receipt import verify_bundle


ROOT = Path(__file__).resolve().parents[1]
REPO = "pilot-owner/checkout-fixture"
APP_ID, INSTALLATION_ID, REPO_ID = 1234, 5678, 9012
SECRET = b"checkout-pilot-test-webhook-secret"
TOKEN = "stub-installation-token"


def pull(number, base, head, *, fork=False):
    return {
        "number": number, "state": "open",
        "base": {"repo": {"id": REPO_ID}, "sha": base},
        "head": {"repo": {"id": REPO_ID + int(fork)}, "sha": head},
    }


class GitHubDouble(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.lock = threading.Lock()
        self.pulls = {}
        self.checks = {}
        self.lost_response = False
        self.check_lookups = []
        self.posts = []

    def move(self, number, base, head):
        with self.lock:
            self.pulls[number] = pull(number, base, head)

    def check(self, commit, conclusion):
        with self.lock:
            return next((row.copy() for row in self.checks.values()
                         if row["head_sha"] == commit and row.get("conclusion") == conclusion), None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["X-GitHub-Api-Version"] == API_VERSION
        if self.path == f"/app/installations/{INSTALLATION_ID}/access_tokens":
            assert self.headers["Authorization"].startswith("Bearer ey")
            assert body["repository_ids"] == [REPO_ID]
            assert body["permissions"] == {"contents": "read", "pull_requests": "read", "checks": "write"}
            self.reply({"token": TOKEN, "expires_at": "2099-01-01T00:00:00Z"}, 201)
            return
        assert self.path == f"/repos/{REPO}/check-runs"
        assert self.headers["Authorization"] == f"Bearer {TOKEN}"
        assert body["name"] == CHECK_NAME
        with self.server.lock:
            check_id = len(self.server.checks) + 1
            row = {"id": check_id, **body, "app": {"id": APP_ID}}
            self.server.checks[check_id] = row
            self.server.posts.append(body["head_sha"])
            if not self.server.lost_response:
                self.server.lost_response = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
        self.reply(row, 201)

    def do_GET(self):
        path = urlsplit(self.path)
        assert self.headers["Authorization"] == f"Bearer {TOKEN}"
        with self.server.lock:
            if path.path.startswith(f"/repos/{REPO}/pulls/"):
                self.reply(self.server.pulls[int(path.path.rsplit("/", 1)[-1])])
                return
            pattern = f"/repos/{REPO}/commits/"
            assert path.path.startswith(pattern) and path.path.endswith("/check-runs")
            query = parse_qs(path.query)
            assert query["check_name"] == [CHECK_NAME] and query["app_id"] == [str(APP_ID)]
            sha = path.path.removeprefix(pattern).removesuffix("/check-runs")
            self.server.check_lookups.append(sha)
            self.reply({"check_runs": [row for row in self.server.checks.values() if row["head_sha"] == sha]})

    def do_PATCH(self):
        assert self.path.startswith(f"/repos/{REPO}/check-runs/")
        assert self.headers["Authorization"] == f"Bearer {TOKEN}"
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with self.server.lock:
            row = self.server.checks[int(self.path.rsplit("/", 1)[-1])]
            assert "head_sha" not in body and body["external_id"] == row["external_id"]
            row.update(body)
            self.reply(row)


def send(origin, number, base, head, *, action="opened", key=None, fork=False, signed=True, repo_id=REPO_ID, code=202):
    key = key or uuid.uuid4()
    body = json.dumps({
        "number": number, "action": action, "pull_request": pull(number, base, head, fork=fork),
        "repository": {"id": repo_id, "full_name": REPO}, "installation": {"id": INSTALLATION_ID},
    }).encode()
    signature = hmac.new(SECRET if signed else b"wrong-key", body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(origin + "/github/webhook", body, headers={
        "Content-Type": "application/json", "X-GitHub-Delivery": str(key), "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": f"sha256={signature}",
    })
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == code, response.read()
        return key, json.load(response).get("disposition")


def commit(repo, parent, text):
    git("-C", str(repo), "switch", "--quiet", "--detach", parent)
    file = repo / "src/checkout.ts"
    file.write_bytes(file.read_bytes() + f"\n// {text}\n".encode())
    git("-C", str(repo), "add", "src/checkout.ts")
    git("-C", str(repo), "-c", "user.name=ReproStamp Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--quiet", "-m", text)
    return git("-C", str(repo), "rev-parse", "HEAD")


def run_for(settings, delivery):
    with connect(settings) as db:
        return db.execute("SELECT run_id FROM github_deliveries WHERE id = %s", (delivery,)).fetchone()["run_id"]


def check_receipt(settings, run_id, expected):
    run = get_run(settings, run_id)
    assert run["verdict"] == expected and len(run["attempts"]) == 12
    bundle = generation_path(settings, run_id, run["fence"]) / "evidence/receipt.zip"
    receipt = verify_bundle(bundle)["payload"]
    assert receipt["verdict"] == expected and receipt["head_sha"] == run["head_sha"]
    return run


def exercise(settings, output, registry, repo):
    migrate(settings)
    base = git("-C", str(repo), "rev-parse", "checkout-base")
    fixed = git("-C", str(repo), "rev-parse", "checkout-fixed")
    bad = commit(repo, base, "Ineffective checkout change")
    interim = commit(repo, fixed, "Interim checkout revision")
    key, secret = output / "stub-key.pem", output / "stub-secret"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)],
                   check=True, capture_output=True, timeout=10)
    secret.write_bytes(SECRET)
    pilot = Pilot(app_id=APP_ID, installation_id=INSTALLATION_ID, repository_id=REPO_ID, repository=REPO,
                  profile_id="checkout", dashboard_url="http://127.0.0.1:3000",
                  webhook_secret_file=str(secret), private_key_file=str(key))
    environment = {**os.environ, "REPROSTAMP_DATABASE_URL": settings.dsn, "REPROSTAMP_DATA": str(settings.data),
                   "REPROSTAMP_REGISTRY": str(registry)}
    with ExitStack() as stack, GitHubDouble() as stub:
        serve = threading.Thread(target=stub.serve_forever, daemon=True)
        serve.start()
        stack.callback(stub.shutdown)
        integration = Integration(settings, pilot, GitHub(pilot, origin=f"http://127.0.0.1:{stub.server_port}"))
        port = available_port()
        server = uvicorn.Server(uvicorn.Config(webhook_app(integration), host="127.0.0.1", port=port,
                                               log_level="warning", access_log=False))
        listener = threading.Thread(target=server.run, daemon=True)
        listener.start()

        def stop_server():
            server.should_exit = True
            listener.join(timeout=10)

        stack.callback(stop_server)
        until(lambda: server.started)
        origin = f"http://127.0.0.1:{port}"
        worker = start(stack, output, "worker", environment, [*CONTROL, "worker"])

        stub.move(1, base, bad)
        send(origin, 1, base, bad, signed=False, code=401)
        assert send(origin, 1, base, bad, fork=True)[1] == "ignored"
        assert send(origin, 1, base, bad, repo_id=REPO_ID + 1)[1] == "ignored"
        with connect(settings) as db:
            assert db.execute("SELECT count(*) AS n FROM github_deliveries").fetchone()["n"] == 0
        delivery, disposition = send(origin, 1, base, bad)
        assert disposition == "accepted" and send(origin, 1, base, bad, key=delivery)[1] == "duplicate"
        print("PASS invalid signature, duplicate delivery, fork and repository allowlist", flush=True)

        failed = until(lambda: stub.check(bad, "failure"), seconds=120)
        failed_run = until(lambda: run_for(settings, delivery))
        check_receipt(settings, failed_run, "FAILED")
        assert failed["details_url"].endswith(str(failed_run))
        assert all(engine in failed["output"]["summary"] for engine in ("chromium", "firefox", "webkit"))
        with stub.lock:
            assert stub.lost_response and stub.posts.count(bad) == 1 and stub.check_lookups.count(bad) >= 2
        print("PASS response lost after check creation, found original check by external ID and published failure", flush=True)

        stub.move(1, base, fixed)
        delivery, _ = send(origin, 1, base, fixed, action="synchronize")
        verified = until(lambda: stub.check(fixed, "success"), seconds=120)
        fixed_run = until(lambda: run_for(settings, delivery))
        check_receipt(settings, fixed_run, "VERIFIED")
        assert verified["details_url"].endswith(str(fixed_run)) and verified["head_sha"] == fixed
        until(lambda: stub.check(bad, "neutral"))
        assert get_run(settings, failed_run)["superseded_at"]
        old, _ = send(origin, 1, base, bad, action="reopened")

        def old_superseded():
            with connect(settings) as db:
                return db.execute("SELECT state, run_id FROM github_deliveries WHERE id = %s", (old,)).fetchone() == {
                    "state": "superseded", "run_id": None,
                }

        until(old_superseded)
        print("PASS subsequent commit received success and the old delivery/evidence was superseded", flush=True)

        stub.move(1, base, interim)
        delivery, _ = send(origin, 1, base, interim, action="synchronize")
        interim_run = until(lambda: run_for(settings, delivery))
        until(lambda: containers(interim_run, 1, running=True))
        # Advance the PR while the runner is active and hold back the webhook.
        # The publisher must refresh the live refs to find the change on its own.
        stub.move(1, base, fixed)
        stale = until(lambda: stub.check(interim, "neutral"), seconds=120)
        assert stale["output"]["title"] == "Evidence superseded"
        assert get_run(settings, interim_run)["superseded_at"] and not stub.check(interim, "success")
        until(lambda: get_run(settings, interim_run)["verdict"] == "VERIFIED", seconds=120)
        check_receipt(settings, interim_run, "VERIFIED")
        with connect(settings) as db:
            assert db.execute("SELECT count(*) AS n FROM runs").fetchone()["n"] == 3
        print("PASS head moved during a real run, ref refresh preserved its receipt and published superseded evidence", flush=True)

        with stub.lock:
            (output / "checks.json").write_text(json.dumps(list(stub.checks.values()), indent=2) + "\n")
        for run_id in (failed_run, fixed_run, interim_run):
            assert not containers(run_id, 1)
        stop(worker)


def main():
    local = Settings.local(ROOT)
    output = Path(tempfile.mkdtemp(prefix="prd04-pilot-", dir=ROOT / ".reprostamp"))
    print(f"Evidence directory: {output}", flush=True)
    logging.basicConfig(filename=output / "integration.log", level=logging.INFO, format="%(asctime)s %(message)s")
    registry, repo, _ = prepare_registry(output)
    database = f"reprostamp_pilot_{uuid.uuid4().hex}"
    with psycopg.connect(local.dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            # Load the same registry in the integration and worker processes.
            os.environ["REPROSTAMP_REGISTRY"] = str(registry)
            registered = Settings.local(ROOT)
            settings = replace(registered, data=output / "data", dsn=make_conninfo(local.dsn, dbname=database))
            exercise(settings, output, registry, repo)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    print(f"PRD-04 local pilot checks passed. Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
