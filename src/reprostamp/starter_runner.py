import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from .integrity import canonical_json, hash_json
from .runner import (COPY_AND_INSTALL, FUNCTIONAL_COMMAND, HARNESS_SETUP, DockerError, IsolatedPair,
                     bind_mount, container_args, docker, read_report, runner_platform)
from .starter_config import StarterConfig


ASSETS = Path(__file__).with_name("starter_assets")
TEMPLATE = ASSETS / "template"
HARNESS = ASSETS / "harness"
IMAGE = (ASSETS / "image.txt").read_text(encoding="ascii").strip()
ENGINES = ("chromium", "firefox", "webkit")
CASE_IDS = ("api.health", "api.tasks", "browser.task-lifecycle")
APP_CASE_IDS = (*CASE_IDS, "browser.presentation")
SETTINGS = {"seed": 42, "locale": "en-US", "timezone": "UTC", "viewport_width": 1100, "viewport_height": 800}
DEPENDENCIES = ("package.json", "package-lock.json", "requirements.lock")
PIP = "26.1.1"
PIP_WHEEL = f"pip-{PIP}-py3-none-any.whl"
APP_COMMAND = COPY_AND_INSTALL + (
    f"PYTHONPATH=/python-cache/{PIP_WHEEL} python3 -m pip --isolated --disable-pip-version-check install "
    "--no-index --only-binary=:all: --find-links=/python-cache --target=/work/python -r requirements.lock; "
    "node node_modules/typescript/bin/tsc --noEmit; node node_modules/vite/bin/vite.js build; "
)
SERVE = "PYTHONPATH=/work/python exec python3 -m uvicorn main:app --host 127.0.0.1 --port 4173"
APP_UNIT = "PYTHONPATH=/work/python python3 -m unittest -v test_app; "


def input_hash(root: Path, names: tuple[str, ...]) -> str:
    return hash_json({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names})


def cache_identity(platform: str) -> dict:
    return {"image": IMAGE, "platform": platform, "pip": PIP,
            "app_dependencies": input_hash(TEMPLATE, DEPENDENCIES),
            "harness_dependencies": input_hash(HARNESS, DEPENDENCIES[:2])}


def check_cache(cache: Path, platform: str) -> None:
    try:
        actual = json.loads((cache / "cache.json").read_bytes())
    except (OSError, ValueError) as error:
        raise ValueError(f"Prepare the starter cache with `reprostamp starter prepare --cache {cache}`.") from error
    if actual != cache_identity(platform) or not (cache / "npm/_cacache").is_dir() or not (cache / "python" / PIP_WHEEL).is_file():
        raise ValueError("The starter cache does not match the pinned runner and dependencies. Prepare a new cache directory.")


def prepare_cache(cache: Path) -> None:
    try:
        platform = runner_platform(IMAGE)
    except DockerError:
        docker("pull", IMAGE, timeout=600)
        platform = runner_platform(IMAGE)
    if cache.exists():
        check_cache(cache, platform)
        return
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="starter-cache-", dir=cache.parent) as temporary:
        staged = Path(temporary) / "cache"
        npm, python = staged / "npm", staged / "python"
        npm.mkdir(parents=True)
        python.mkdir()
        subprocess.run([
            sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check", "download", "--no-deps",
            "--only-binary=:all:", "--index-url=https://pypi.org/simple", "--dest", str(python), f"pip=={PIP}",
        ], check=True, timeout=90)
        locks = Path(temporary) / "locks"
        locks.mkdir()
        for name, source in (("app", TEMPLATE), ("harness", HARNESS)):
            destination = locks / name
            destination.mkdir()
            for filename in DEPENDENCIES:
                if (source / filename).is_file():
                    shutil.copyfile(source / filename, destination / filename)
        docker(
            "run", "--rm", "--init", "--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--cpus=2", "--memory=1g", "--pids-limit=256", "--user", f"{os.getuid()}:{os.getgid()}",
            "--tmpfs=/tmp:rw,nosuid,nodev,exec,size=768m,mode=1777", "--env=HOME=/tmp", "--workdir=/tmp",
            "--mount", bind_mount(locks, "/locks"), "--mount", bind_mount(npm, "/npm", read_only=False),
            "--mount", bind_mount(python, "/wheels", read_only=False), IMAGE, "sh", "-ec",
            "for project in app harness; do mkdir \"$project\"; cp /locks/\"$project\"/package*.json \"$project\"/; "
            "(cd \"$project\" && npm ci --ignore-scripts --include=dev --no-audit --no-fund --cache /npm); done; "
            f"PYTHONPATH=/wheels/{PIP_WHEEL} python3 -m pip --isolated --disable-pip-version-check download "
            "--only-binary=:all: --index-url=https://pypi.org/simple --dest /wheels -r /locks/app/requirements.lock",
            timeout=240,
        )
        (staged / "cache.json").write_bytes(canonical_json(cache_identity(platform)))
        staged.rename(cache)


def run_engine(engine: str, run_id: str, source: Path, config: StarterConfig, cache: Path,
               harness: Path, temporary: Path, out: Path, *, presentation: dict | None = None) -> dict:
    started = time.monotonic()
    pair = IsolatedPair(60)
    output = out / engine
    output.mkdir()
    evidence = temporary / engine
    evidence.mkdir(mode=0o777)
    evidence.chmod(0o777)  # Only the harness receives the writable evidence mount.
    phase = "startup"
    reason = detail = status = None
    npm_cache = cache / "npm/_cacache"
    app_checks = APP_UNIT if presentation is not None else ""
    presentation_env = [] if presentation is None else [
        f"--env=REPROSTAMP_APP_PRESENTATION={json.dumps(presentation)}",
    ]
    try:
        pair.create("app", pair.app, *container_args(pair.app, "none", run_id, source, npm_cache),
                    "--mount", bind_mount(cache / "python", "/python-cache"), IMAGE, "sh", "-ec", APP_COMMAND + app_checks + SERVE)
        pair.command("start", pair.app)
        pair.create("harness", pair.harness,
                    *container_args(pair.harness, f"container:{pair.app}", run_id, harness, npm_cache),
                    "--mount", bind_mount(evidence, "/evidence", read_only=False),
                    f"--env=REPROSTAMP_BROWSER_SETTINGS={json.dumps(SETTINGS)}", f"--env=REPROSTAMP_ENGINE={engine}",
                    f"--env=REPROSTAMP_STARTER_CONFIG={json.dumps(asdict(config), ensure_ascii=False)}",
                    *presentation_env, IMAGE, "sh", "-ec", HARNESS_SETUP + "exec " + FUNCTIONAL_COMMAND)
        pair.command("start", pair.harness)
        phase = "execution"
        status = pair.command("wait", pair.harness)
    except subprocess.TimeoutExpired:
        reason, detail = "attempt_timeout", "Validation exceeded its 60-second deadline."
    except DockerError as error:
        reason, detail = f"runner_{phase}_failed", str(error)
    finally:
        logs, cleanup_errors = pair.collect(output, out)
    cases, build = [], None
    if (evidence / "report.json").is_file():
        cases, build, report_reason, report_detail = read_report(
            evidence, output, out, frozenset(APP_CASE_IDS if presentation is not None else CASE_IDS), engine,
            require_failure_artifacts=False,
        )
        if reason is None:
            reason, detail = report_reason, report_detail
        if reason is None:
            expected_status = "1" if any(case.status == "assertion_failed" for case in cases) else "0"
            if status != expected_status:
                reason, detail = "harness_incomplete", f"Unexpected harness exit status {status}."
    elif reason is None:
        reason, detail = "harness_incomplete", "No acceptance report was produced. See the app and harness logs."
    if cleanup_errors:
        reason, detail = "runner_cleanup_failed", "\n".join(cleanup_errors)
    return {"engine": engine, "execution_state": "incomplete" if reason else "completed",
            "reason": reason, "detail": detail, "duration_ms": round((time.monotonic() - started) * 1000),
            "browser_build": asdict(build) if build else None, "checks": [asdict(case) for case in cases], "logs": logs}
