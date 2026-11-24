import hashlib
import hmac
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..control.database import connect
from .client import pr_refs
from .integration import Integration


EVENTS = frozenset(("opened", "reopened", "synchronize"))
BODY_LIMIT = 1024 * 1024


def webhook_app(integration: Integration) -> FastAPI:
    pilot = integration.pilot
    secret = Path(pilot.webhook_secret_file).read_bytes().rstrip(b"\r\n")
    if not secret:
        raise ValueError("The GitHub webhook secret file is empty.")

    @asynccontextmanager
    async def lifespan(_app):
        with connect(integration.settings) as db:
            db.execute("SELECT 1 FROM github_deliveries LIMIT 1")
        stop = threading.Event()
        worker = threading.Thread(target=integration.work, args=(stop,), daemon=True)
        worker.start()
        try:
            yield
        finally:
            stop.set()

    app = FastAPI(title="ReproStamp GitHub App", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.post("/github/webhook", status_code=202)
    async def webhook(request: Request):
        signature = request.headers.get("X-Hub-Signature-256", "")
        if len(signature) != 71 or not signature.startswith("sha256="):
            raise HTTPException(401, "Invalid webhook signature.")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > BODY_LIMIT:
                raise HTTPException(413, "Webhook body is too large.")
            body.extend(chunk)
        expected = b"sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(expected, signature.encode()):
            raise HTTPException(401, "Invalid webhook signature.")
        if request.headers.get("X-GitHub-Event") != "pull_request":
            return {"disposition": "ignored"}

        try:
            delivery = UUID(request.headers["X-GitHub-Delivery"])
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError
        except (KeyError, ValueError):
            raise HTTPException(400, "Malformed GitHub delivery.") from None
        action = payload.get("action")
        if not isinstance(action, str) or action not in EVENTS:
            return {"disposition": "ignored"}
        repo = payload.get("repository")
        install = payload.get("installation")
        if (not isinstance(repo, dict) or not isinstance(install, dict) or repo.get("id") != pilot.repository_id
            or install.get("id") != pilot.installation_id or str(repo.get("full_name", "")).lower() != pilot.repository.lower()):
            return {"disposition": "ignored"}
        if not (refs := pr_refs(payload.get("pull_request"), pilot.repository_id)):
            return {"disposition": "ignored"}
        number = payload.get("number")
        if type(number) is not int or not 0 < number < 2**63:
            raise HTTPException(400, "Invalid pull request number.")

        created = await run_in_threadpool(integration.state.receive, delivery, number, *refs)
        return {"disposition": "accepted" if created else "duplicate"}

    return app
