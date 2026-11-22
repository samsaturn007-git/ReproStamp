import csv
import io
import json
import shutil
import stat
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .profile import PolicyError, Profile


RUNNER_CONTRACT = 1
PROXY_VARIABLES = tuple(
    case for variable in ("HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "NO_PROXY", "ALL_PROXY")
    for case in (variable, variable.lower())
)
COPY_AND_INSTALL = (
    f"unset {' '.join(PROXY_VARIABLES)}; "
    "cp -R /inputs/. /work/; mkdir -p /tmp/npm-cache; "
    "cp -R /npm-cache /tmp/npm-cache/_cacache; "
    "npm ci --offline --ignore-scripts --include=dev --no-audit --no-fund --cache /tmp/npm-cache; "
)
APP_COMMAND = COPY_AND_INSTALL + "exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173 --strictPort"
HARNESS_COMMAND = COPY_AND_INSTALL + (
    "node wait-for-app.cjs; exec node node_modules/@playwright/test/cli.js test --config playwright.config.cjs"
)
ARTIFACT_NAMES = {"trace": "trace.zip", "screenshot": "screenshot.png"}
HOME_OVERRIDES = ["--env=HOME=/tmp", "--env=CI=1"]
PROXY_OVERRIDES = [f"--env={variable}=" for variable in PROXY_VARIABLES]


class DockerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Assertion:
    id: str
    actual: str | None
    expected: str


@dataclass(frozen=True)
class Case:
    case_id: str
    status: str
    playwright_status: str
    duration_ms: int
    assertion: Assertion | None
    artifacts: dict[str, str]
    detail: str | None


@dataclass(frozen=True)
class BrowserBuild:
    version: str
    platform: str


@dataclass(frozen=True)
class Attempt:
    side: str
    number: int
    commit: str
    engine: str
    status: str
    duration_ms: int
    reason: str | None
    detail: str | None
    cases: list[Case]
    logs: dict[str, str]
    browser_build: BrowserBuild | None


def freeze_harness(source: Path, target: Path) -> None:
    target.mkdir()
    target.chmod(0o755)
    excluded = {"node_modules", ".git", "test-results", "playwright-report", ".DS_Store", ".npmrc"}
    for path in sorted(source.iterdir()):
        if path.name in excluded or path.name.startswith(".env"):
            continue
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            freeze_harness(path, target / path.name)
        elif stat.S_ISREG(mode):
            output = target / path.name
            shutil.copyfile(path, output)
            output.chmod(0o644)
        else:
            raise PolicyError("unsupported_harness_entry", f"Unsupported harness entry {path.name!r}.")


def bind_mount(source: Path, target: str, *, read_only: bool = True) -> str:
    fields = ["type=bind", f"source={source}", f"target={target}"]
    if read_only:
        fields.append("readonly")
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="").writerow(fields)
    return buffer.getvalue()


def docker(*args: str, timeout: float, merge_stderr: bool = False) -> str:
    if timeout <= 0:
        raise subprocess.TimeoutExpired(args, timeout)
    try:
        return subprocess.run(
            ["docker", *args], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True, errors="replace", timeout=timeout,
        ).stdout
    except subprocess.CalledProcessError as error:
        message = (error.stderr or error.stdout or "").strip()
        raise DockerError(message or f"Docker exited with status {error.returncode}.") from error
    except OSError as error:
        raise DockerError(str(error)) from error


def container_args(name: str, network: str, run_id: str, source: Path, cache: Path) -> list[str]:
    return [
        "--name", name, "--label", f"io.reprostamp.run={run_id}",
        "--network", network, "--pull=never", "--init", "--user=pwuser", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=2", "--memory=1g",
        "--pids-limit=256", "--shm-size=256m", "--log-driver=local", "--log-opt=max-size=1m",
        "--log-opt=max-file=2", "--tmpfs=/tmp:rw,nosuid,nodev,size=512m,mode=1777",
        "--tmpfs=/work:rw,nosuid,nodev,exec,size=512m,mode=1777", "--workdir=/work",
        *HOME_OVERRIDES, *PROXY_OVERRIDES,
        "--mount", bind_mount(source, "/inputs"), "--mount", bind_mount(cache, "/npm-cache"),
    ]


def read_report(
    source: Path, output: Path, root: Path, profile: Profile, engine: str,
) -> tuple[list[Case], BrowserBuild | None, str | None, str | None]:
    cases = []
    build = None
    try:
        report = json.loads((source / "report.json").read_text(encoding="utf-8"))
        builds = report.get("builds", [])
        if builds:
            if len(builds) != 1 or builds[0]["engine"] != engine:
                raise ValueError(f"Expected one observed {engine} build, received {builds!r}.")
            version, platform = builds[0]["version"], builds[0]["platform"]
            if any(not isinstance(field, str) or not field.strip() for field in (version, platform)):
                raise ValueError("Invalid browser build metadata.")
            build = BrowserBuild(version, platform)
        seen = set()
        for entry in report["cases"]:
            case_id = entry["case_id"]
            if case_id not in profile.case_ids or case_id in seen:
                raise ValueError(f"Unexpected or duplicate case {case_id!r}.")
            seen.add(case_id)
            raw_status = entry["status"]
            duration = entry["duration_ms"]
            if type(duration) is not int or duration < 0:
                raise ValueError(f"Invalid duration for {case_id}.")
            status = "passed" if raw_status == "passed" else "error"
            if raw_status == "skipped":
                status = "missing"
            assertion = None
            if raw_status == "failed" and entry["assertion"] is not None:
                marker = entry["assertion"]
                assertion = Assertion(marker["id"], marker["actual"], marker["expected"])
                if not isinstance(assertion.id, str) or not isinstance(assertion.expected, str) or (
                    assertion.actual is not None and not isinstance(assertion.actual, str)
                ):
                    raise ValueError(f"Invalid assertion in {case_id}.")
                status = "assertion_failed"
            detail = None
            if status in ("missing", "error"):
                detail = entry.get("error") or f"Playwright ended as {raw_status} without an assertion marker."
                if build is None and "executable doesn't exist at" in detail.lower():
                    status = "unsupported"

            artifacts = {}
            for kind, filename in ARTIFACT_NAMES.items():
                if kind not in entry["artifacts"]:
                    continue
                artifact = (source / entry["artifacts"][kind]).resolve()
                if not artifact.is_relative_to(source.resolve()) or not artifact.is_file() or not artifact.stat().st_size:
                    raise ValueError(f"Invalid {kind} for {case_id}.")
                destination = output / case_id / filename
                destination.parent.mkdir(exist_ok=True)
                shutil.copyfile(artifact, destination)
                artifacts[kind] = destination.relative_to(root).as_posix()
            cases.append(Case(case_id, status, raw_status, duration, assertion, artifacts, detail))

        if any(case.status == "unsupported" for case in cases):
            return cases, build, "required_engine_unsupported", f"The {engine} executable is unavailable in the runner."
        missing = (profile.case_ids - seen) | {case.case_id for case in cases if case.status == "missing"}
        if missing:
            return cases, build, "required_cell_missing", f"Missing cases: {', '.join(sorted(missing))}."
        if report["status"] not in ("passed", "failed") or report["errors"]:
            raise ValueError(f"Playwright reported {report['status']}: {report['errors']}")
        for case in cases:
            if case.status == "error":
                raise ValueError(f"{case.case_id} ended as {case.playwright_status} without a completed assertion.")
            if case.status == "assertion_failed" and case.artifacts.keys() != ARTIFACT_NAMES.keys():
                raise ValueError(f"{case.case_id} is missing a failure trace or screenshot.")
        if build is None:
            return cases, None, "browser_build_missing", f"The harness did not record the launched {engine} build."
    except (KeyError, OSError, TypeError, ValueError) as error:
        return cases, build, "harness_incomplete", str(error)
    return cases, build, None, None


def runner_platform(image: str) -> str:
    return docker("image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", image, timeout=10).strip()


def run_attempt(
    profile: Profile, *, run_id: str, side: str, number: int, commit: str, engine: str,
    app: Path, harness: Path, work_root: Path, out_root: Path,
) -> Attempt:
    started = time.monotonic()
    deadline = started + profile.timeout_seconds
    output = out_root / engine / side / f"attempt-{number}"
    output.mkdir(parents=True)
    evidence = work_root / f"{engine}-{side}-{number}"
    evidence.mkdir()
    evidence.chmod(0o777)  # Writable by pwuser inside a bind whose host parent is private.
    prefix = f"reprostamp-{uuid.uuid4().hex}"
    app_name, harness_name = f"{prefix}-app", f"{prefix}-harness"
    cache = profile.npm_cache / "_cacache"
    containers = {}
    logs = {}
    cleanup_errors = []
    reason = detail = None
    exit_status = None
    phase = "startup"

    def command(*args: str) -> str:
        return docker(*args, timeout=deadline - time.monotonic()).strip()

    def create(role: str, name: str, *args: str) -> None:
        try:
            command("create", *args)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            containers[role] = name  # The daemon may have accepted the create request.
            raise
        containers[role] = name

    try:
        create("app", app_name, *container_args(app_name, "none", run_id, app, cache),
               profile.runner_image, "sh", "-ec", APP_COMMAND)
        command("start", app_name)
        create("harness", harness_name, *container_args(harness_name, f"container:{app_name}", run_id, harness, cache),
               f"--env=REPROSTAMP_ENGINE={engine}",
               f"--env=REPROSTAMP_BROWSER_SETTINGS={json.dumps(asdict(profile.browser), ensure_ascii=False)}",
               "--mount", bind_mount(evidence, "/evidence", read_only=False),
               profile.runner_image, "sh", "-ec", HARNESS_COMMAND)
        command("start", harness_name)
        phase = "execution"
        exit_status = command("wait", harness_name)
    except subprocess.TimeoutExpired:
        reason, detail = "attempt_timeout", f"The attempt exceeded its {profile.timeout_seconds}s deadline."
    except DockerError as error:
        reason, detail = f"runner_{phase}_failed", str(error)
    finally:
        for role, name in reversed(containers.items()):
            try:
                docker("stop", "--time=0", name, timeout=5)
            except (DockerError, subprocess.TimeoutExpired):
                pass  # Force-removal below also stops a workload that is still running.
            try:
                log = docker("logs", name, timeout=5, merge_stderr=True)
                log_path = output / f"{role}.log"
                log_path.write_text(log, encoding="utf-8")
                logs[role] = log_path.relative_to(out_root).as_posix()
            except (DockerError, OSError, subprocess.TimeoutExpired):
                pass
            try:
                docker("rm", "--force", name, timeout=5)
            except (DockerError, subprocess.TimeoutExpired) as error:
                if "No such container" not in str(error):
                    cleanup_errors.append(f"{name}: {error}")

    if reason is None and not (evidence / "report.json").is_file():
        reason = "runner_startup_failed" if exit_status == "1" else "harness_incomplete"
        detail = f"The harness exited with status {exit_status} without producing a report. See attempt logs."
    cases, build, report_reason, report_detail = [], None, None, None
    if (evidence / "report.json").is_file():
        cases, build, report_reason, report_detail = read_report(evidence, output, out_root, profile, engine)
    if reason is None:
        reason, detail = report_reason, report_detail
        if reason is None and exit_status not in ("0", "1"):
            reason, detail = "harness_incomplete", f"Unexpected harness exit status {exit_status}."
    if cleanup_errors:
        reason, detail = "runner_cleanup_failed", "\n".join(cleanup_errors)
    return Attempt(
        side, number, commit, engine, "completed" if reason is None else "incomplete",
        round((time.monotonic() - started) * 1000), reason, detail, cases, logs, build,
    )
