import re

from .profile import CASE_ID, ENGINES, IMAGE
from .repository import OBJECT_ID
from .runner import ARTIFACT_NAMES
from .verdict import EXIT_CODES


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PLATFORM = re.compile(r"[a-z0-9]+/[a-z0-9]+")
REASON = re.compile(r"[a-z][a-z0-9_]*")
SIDES = ("base", "head")
NUMBERS = (1, 2)
CASE_OUTCOMES = ("passed", "assertion_failed", "error", "missing", "unsupported")


def record(value, fields: str, label: str) -> None:
    if not isinstance(value, dict) or value.keys() != set(fields.split()):
        raise ValueError(f"Invalid {label} fields.")


def string(value, label: str, pattern=None) -> None:
    if not isinstance(value, str) or (pattern is not None and not pattern.fullmatch(value)):
        raise ValueError(f"Invalid {label}.")


def integer(value, low: int, high: int, label: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Invalid {label}.")


def enum(value, choices, label: str) -> None:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"Invalid {label}.")


def validate_inputs(inputs: dict) -> None:
    record(inputs, "repository_sha256 diff_sha256 lockfile_sha256 oracle_sha256 profile_sha256 "
           "runner_image runner_platform runner_contract settings", "run inputs")
    for field in ("repository_sha256", "diff_sha256", "oracle_sha256", "profile_sha256"):
        string(inputs[field], field, SHA256)
    record(inputs["lockfile_sha256"], "base head", "lockfile hashes")
    for side in SIDES:
        string(inputs["lockfile_sha256"][side], f"{side} lockfile hash", SHA256)
    string(inputs["runner_image"], "runner image", IMAGE)
    if inputs["runner_platform"] is not None:
        string(inputs["runner_platform"], "runner platform", PLATFORM)
    integer(inputs["runner_contract"], 1, 2**31, "runner contract version")
    settings = inputs["settings"]
    record(settings, "seed viewport_width viewport_height locale timezone timeout_seconds attempts_per_side", "settings")
    integer(settings["seed"], 0, 2**32 - 1, "seed")
    for field in ("viewport_width", "viewport_height"):
        integer(settings[field], 1, 4096, field)
    for field in ("locale", "timezone"):
        string(settings[field], field)
    integer(settings["timeout_seconds"], 1, 120, "attempt deadline")
    integer(settings["attempts_per_side"], len(NUMBERS), len(NUMBERS), "attempt count")


def validate_artifact_paths(entries, allowed: dict[str, str], label: str) -> set[str]:
    if not isinstance(entries, dict) or not entries.keys() <= allowed.keys():
        raise ValueError(f"Unexpected {label} entries.")
    if any(path != allowed[kind] for kind, path in entries.items()):
        raise ValueError(f"Unsafe or misplaced {label} path.")
    return set(entries.values())


def validate_attempt(attempt, plan: dict, payload: dict) -> tuple[tuple, set[str]]:
    record(attempt, "side number commit engine status duration_ms reason detail cases logs browser_build", "attempt")
    side, engine, number = attempt["side"], attempt["engine"], attempt["number"]
    enum(side, SIDES, "attempt side")
    enum(engine, plan["engines"], "attempt engine")
    integer(number, 1, len(NUMBERS), "attempt number")
    string(attempt["commit"], "attempt commit", OBJECT_ID)
    if attempt["commit"] != payload[f"{side}_sha"]:
        raise ValueError("Attempt commit does not match the receipt.")
    enum(attempt["status"], ("completed", "incomplete"), "attempt status")
    integer(attempt["duration_ms"], 0, 2**53 - 1, "attempt duration")
    completed = attempt["status"] == "completed"
    if completed:
        if attempt["reason"] is not None or attempt["detail"] is not None:
            raise ValueError("A completed attempt cannot have an execution error.")
    else:
        string(attempt["reason"], "attempt reason", REASON)
        string(attempt["detail"], "attempt detail")
    build = attempt["browser_build"]
    if build is not None or completed:
        record(build, "version platform", "browser build")
        string(build["version"], "browser version")
        string(build["platform"], "browser platform", PLATFORM)

    prefix = f"{engine}/{side}/attempt-{number}"
    paths = validate_artifact_paths(attempt["logs"], {role: f"{prefix}/{role}.log" for role in ("app", "harness")}, "log")
    cases = attempt["cases"]
    if not isinstance(cases, list):
        raise ValueError("Attempt cases must be a list.")
    seen = set()
    for case in cases:
        record(case, "case_id status playwright_status duration_ms assertion artifacts detail", "case")
        case_id = case["case_id"]
        enum(case_id, plan["case_ids"], "case ID")
        if case_id in seen:
            raise ValueError(f"Duplicate case {case_id} in {prefix}.")
        seen.add(case_id)
        enum(case["status"], CASE_OUTCOMES, "case outcome")
        if completed and case["status"] not in ("passed", "assertion_failed"):
            raise ValueError("Completed attempts must contain completed assertions.")
        enum(case["playwright_status"], ("passed", "failed", "timedOut", "skipped", "interrupted"), "Playwright status")
        integer(case["duration_ms"], 0, 2**53 - 1, "case duration")
        if case["detail"] is not None:
            string(case["detail"], "case detail")
        assertion = case["assertion"]
        if case["status"] == "assertion_failed":
            record(assertion, "id actual expected", "assertion")
            for field in ("id", "expected"):
                string(assertion[field], f"assertion {field}")
            if assertion["actual"] is not None:
                string(assertion["actual"], "assertion actual")
        elif assertion is not None:
            raise ValueError("An assertion marker requires an assertion failure.")
        allowed = {kind: f"{prefix}/{case_id}/{name}" for kind, name in ARTIFACT_NAMES.items()}
        paths |= validate_artifact_paths(case["artifacts"], allowed, "case artifact")
        if completed and assertion is not None and case["artifacts"].keys() != allowed.keys():
            raise ValueError("Completed assertion failures require a trace and screenshot.")
    if completed and seen != set(plan["case_ids"]):
        raise ValueError("Completed attempt is missing required cases.")
    return (engine, side, number), paths


def validate_payload(payload: dict) -> None:
    record(payload, "run_id replay_of base_sha head_sha plan inputs execution_state verdict reason detail "
           "engine_verdicts attempts artifacts", "receipt payload")
    string(payload["run_id"], "run ID", re.compile(r"[0-9a-f]{32}"))
    if payload["replay_of"] is not None:
        string(payload["replay_of"], "original receipt hash", SHA256)
    for side in SIDES:
        if payload[f"{side}_sha"] is not None or payload["inputs"] is not None:
            string(payload[f"{side}_sha"], f"{side} SHA", OBJECT_ID)
    enum(payload["execution_state"], ("completed", "incomplete", "blocked"), "execution state")
    enum(payload["verdict"], EXIT_CODES, "verdict")
    if (payload["execution_state"] == "blocked") != (payload["verdict"] == "POLICY_BLOCKED"):
        raise ValueError("A policy verdict requires blocked execution.")
    if payload["verdict"] in ("VERIFIED", "FAILED") and payload["execution_state"] != "completed":
        raise ValueError("An assertion verdict requires completed execution.")
    string(payload["reason"], "verdict reason", REASON)
    string(payload["detail"], "verdict detail")
    plan = payload["plan"]
    record(plan, "engines case_ids", "run plan")
    for field in ("engines", "case_ids"):
        if not isinstance(plan[field], list):
            raise ValueError(f"Invalid plan {field}.")
        for item in plan[field]:
            if field == "engines":
                enum(item, ENGINES, "required engine")
            else:
                string(item, "case ID", CASE_ID)
        if len({item.casefold() for item in plan[field]}) != len(plan[field]):
            raise ValueError(f"Duplicate plan {field}.")
    if bool(plan["case_ids"]) != bool(plan["engines"]):
        raise ValueError("The plan requires both engines and cases.")
    if payload["inputs"] is not None:
        validate_inputs(payload["inputs"])
        if not plan["engines"]:
            raise ValueError("Recorded run inputs require a plan.")
    engine_verdicts = payload["engine_verdicts"]
    if not isinstance(engine_verdicts, dict) or not engine_verdicts.keys() <= set(plan["engines"]):
        raise ValueError("Invalid engine verdicts.")
    for verdict in engine_verdicts.values():
        record(verdict, "name reason detail", "engine verdict")
        enum(verdict["name"], EXIT_CODES, "engine verdict")
        string(verdict["reason"], "engine verdict reason", REASON)
        string(verdict["detail"], "engine verdict detail")

    attempts = payload["attempts"]
    if not isinstance(attempts, list) or (attempts and payload["inputs"] is None):
        raise ValueError("Invalid attempts for the recorded inputs.")
    expected_paths = {"receipt.md"}
    seen = set()
    for attempt in attempts:
        key, paths = validate_attempt(attempt, plan, payload)
        if key in seen:
            raise ValueError(f"Duplicate attempt {key}.")
        seen.add(key)
        expected_paths |= paths
    if payload["execution_state"] == "completed" and (
        not plan["engines"] or len(seen) != len(plan["engines"]) * len(SIDES) * len(NUMBERS)
        or any(attempt["status"] != "completed" for attempt in attempts)
    ):
        raise ValueError("Completed run is missing required attempt evidence.")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, dict) or artifacts.keys() != expected_paths:
        raise ValueError("Artifact manifest must match the approved evidence paths.")
    for path, metadata in artifacts.items():
        record(metadata, "size sha256", f"metadata for {path}")
        integer(metadata["size"], 0, 2**53 - 1, "artifact size")
        string(metadata["sha256"], "artifact hash", SHA256)
