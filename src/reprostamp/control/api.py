import asyncio
import hmac
import json
import subprocess
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import APIKeyCookie
from starlette.concurrency import run_in_threadpool

from ..profile import PolicyError
from ..repository import RepositoryError
from . import schema, store
from .settings import Settings


COOKIE = "reprostamp_owner"
PREFIX = "/api/v1"
OWNER_COOKIE = APIKeyCookie(name=COOKIE, scheme_name="OwnerSession", auto_error=False)
DOWNLOAD_FORMATS = {"receipt": "application/zip", "trace": "application/zip", "screenshot": "image/png",
                    "log": "text/plain"}
DOWNLOAD_SCHEMA = {"schema": {"type": "string", "format": "binary"}}


def create_app(settings: Settings | None = None, *, describe: bool = False) -> FastAPI:
    app = FastAPI(title="ReproStamp local API", version="1.0.0",
                  openapi_url=PREFIX + "/openapi.json", docs_url=PREFIX + "/docs", redoc_url=None)
    password = settings.owner_password() if settings and not describe else None

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "private, no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def same_origin(request: Request) -> None:
        if request.headers.get("origin") != settings.origin:
            raise HTTPException(403, "The dashboard origin does not match the configured owner origin.")

    def owner(token: Annotated[str | None, Depends(OWNER_COOKIE)]) -> str:
        csrf = store.session(settings, token)
        if csrf is None:
            raise HTTPException(401, "Owner sign-in required.")
        return csrf

    def owner_write(request: Request, csrf: Annotated[str, Depends(owner)],
                    token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None) -> None:
        same_origin(request)
        if token is None or not hmac.compare_digest(token.encode(), csrf.encode()):
            raise HTTPException(403, "CSRF token missing or invalid.")

    @app.post(PREFIX + "/session", response_model=schema.Session)
    def login(body: schema.Login, request: Request, response: Response):
        same_origin(request)
        if not hmac.compare_digest(body.password.encode(), password.encode()):
            raise HTTPException(401, "Incorrect owner password.")
        if prior := request.cookies.get(COOKIE):
            store.delete_session(settings, prior)
        token, csrf = store.create_session(settings)
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=43200, path=PREFIX,
                            secure=settings.origin.startswith("https://"))
        return schema.Session(csrf_token=csrf)

    @app.get(PREFIX + "/session", response_model=schema.Session)
    def get_session(csrf: Annotated[str, Depends(owner)]):
        return schema.Session(csrf_token=csrf)

    @app.delete(PREFIX + "/session", status_code=204, dependencies=[Depends(owner_write)])
    def logout(request: Request, response: Response):
        store.delete_session(settings, request.cookies[COOKIE])
        response.delete_cookie(COOKIE, path=PREFIX, httponly=True, samesite="strict",
                               secure=settings.origin.startswith("https://"))

    @app.get(PREFIX + "/registry", response_model=schema.Registry, dependencies=[Depends(owner)])
    def registry():
        return schema.Registry(
            repositories=[schema.RepositoryChoice(id=item.id, label=item.label)
                          for item in settings.repositories.values()],
            profiles=[schema.ProfileChoice(id=item.id, label=item.label, repo_id=item.repo_id,
                                           base=item.base, head=item.head) for item in settings.profiles.values()],
        )

    @app.post(PREFIX + "/runs", response_model=schema.RunSummary, status_code=201,
              responses={200: {"model": schema.RunSummary}}, dependencies=[Depends(owner_write)])
    def submit(body: schema.NewRun, response: Response, key: Annotated[UUID, Header(alias="Idempotency-Key")]):
        profile = settings.profiles.get(body.profile_id)
        if profile is None or profile.repo_id != body.repo_id:
            raise HTTPException(404, "This repository and profile are not registered together.")
        try:
            row, created = store.submit(settings, key, body.model_dump())
        except store.SubmissionConflict as error:
            raise HTTPException(409, str(error)) from error
        except (PolicyError, RepositoryError, OSError, subprocess.SubprocessError) as error:
            raise HTTPException(422, f"Could not freeze registered inputs. {error}") from error
        if not created:
            response.status_code = 200
        response.headers["Location"] = f"{PREFIX}/runs/{row['id']}"
        return row

    @app.get(PREFIX + "/runs", response_model=list[schema.RunSummary], dependencies=[Depends(owner)])
    def list_runs():
        return store.runs(settings)

    @app.get(PREFIX + "/runs/{run_id}", response_model=schema.RunDetail, dependencies=[Depends(owner)])
    def detail(run_id: UUID):
        row = store.get_run(settings, run_id)
        if row is None:
            raise HTTPException(404, "Run not found.")
        return row

    @app.post(PREFIX + "/runs/{run_id}/cancel", response_model=schema.RunSummary, dependencies=[Depends(owner_write)])
    def cancel(run_id: UUID):
        row = store.cancel(settings, run_id)
        if row is None:
            raise HTTPException(404, "Run not found.")
        return row

    @app.get(PREFIX + "/runs/{run_id}/events", response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
             dependencies=[Depends(owner)])
    def timeline(run_id: UUID, request: Request,
                 last: Annotated[int, Header(alias="Last-Event-ID", ge=0, le=2**63 - 1)] = 0):
        detail(run_id)

        async def stream():
            cursor = last
            cookie = request.cookies.get(COOKIE)
            yield "retry: 1200\n\n"
            idle = 0
            while not await request.is_disconnected():
                if not await run_in_threadpool(store.session, settings, cookie):
                    return
                batch, terminal = await run_in_threadpool(store.events, settings, run_id, cursor)
                for item in batch:
                    event = schema.RunEvent.model_validate(item)
                    cursor = event.seq
                    yield f"id: {cursor}\ndata: {event.model_dump_json()}\n\n"
                if terminal:
                    yield "event: timeline-complete\ndata: {}\n\n"
                    return
                if not batch:
                    idle += 1
                    if idle % 10 == 0:
                        yield ": keep-alive\n\n"
                    await asyncio.sleep(0.65)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "private, no-store, no-transform"})

    @app.get(PREFIX + "/runs/{run_id}/timeline", response_model=schema.Timeline, dependencies=[Depends(owner)])
    def timeline_snapshot(run_id: UUID, after: int = 0):
        detail(run_id)
        if not 0 <= after <= 2**63 - 1:
            raise HTTPException(422, "Invalid event cursor.")
        batch, terminal = store.events(settings, run_id, after)
        return {"events": batch, "terminal": terminal}

    def download(run_id: UUID, artifact_id: UUID | None = None):
        item = store.artifact(settings, run_id, artifact_id)
        if item is None:
            raise HTTPException(404, "Evidence not found.")
        if item["expired"]:
            raise HTTPException(410, "The evidence retention period has ended.")
        root = store.generation_path(settings, run_id, item["fence"]) / "evidence"
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, "Evidence file is unavailable.")
        return FileResponse(path, media_type=DOWNLOAD_FORMATS[item["kind"]], filename=Path(item["path"]).name,
                            headers={"Content-Security-Policy": "sandbox"})

    @app.get(PREFIX + "/runs/{run_id}/receipt", response_class=FileResponse, dependencies=[Depends(owner)],
             responses={200: {"content": {"application/zip": DOWNLOAD_SCHEMA}}})
    def receipt(run_id: UUID):
        return download(run_id)

    @app.get(PREFIX + "/runs/{run_id}/artifacts/{artifact_id}", response_class=FileResponse,
             dependencies=[Depends(owner)],
             responses={200: {"content": {mime: DOWNLOAD_SCHEMA for mime in DOWNLOAD_FORMATS.values()}}})
    def artifact(run_id: UUID, artifact_id: UUID):
        return download(run_id, artifact_id)

    return app
