import re
from datetime import datetime
from uuid import UUID

from .profile import CASE_ID, ENGINES, IMAGE, review_plan
from .repository import OBJECT_ID
from .review import AXE_VERSION, MAX_PNG_BYTES, REVIEW_FILES, findings_from_report
from .runner import APPLICATION_LOCATION, ARTIFACT_NAMES
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
        fields = "case_id status playwright_status duration_ms assertion artifacts detail"
        if isinstance(case, dict) and "application_location" in case:
            fields += " application_location"
            string(case["application_location"], "application stack location", APPLICATION_LOCATION)
        record(case, fields, "case")
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
    fields = ("run_id replay_of base_sha head_sha plan inputs execution_state verdict reason detail "
              "engine_verdicts attempts artifacts")
    if isinstance(payload, dict) and "reviews" in payload:
        fields += " reviews"
    record(payload, fields, "receipt payload")
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
    has_review = isinstance(plan, dict) and "review" in plan
    record(plan, "engines case_ids review" if has_review else "engines case_ids", "run plan")
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
    if not isinstance(artifacts, dict):
        raise ValueError("Invalid artifact manifest.")
    for path, metadata in artifacts.items():
        record(metadata, "size sha256", f"metadata for {path}")
        integer(metadata["size"], 0, 2**53 - 1, "artifact size")
        string(metadata["sha256"], "artifact hash", SHA256)
    if has_review:
        try:
            planned_review = review_plan(plan["review"], plan["engines"])
        except TypeError as error:
            raise ValueError("Invalid route review plan.") from error
        if "reviews" in payload:
            expected_paths |= validate_reviews(payload, planned_review)
        elif payload["execution_state"] == "completed":
            raise ValueError("A completed run must report every configured review.")
    elif "reviews" in payload:
        raise ValueError("Route review results require a configured review plan.")
    if artifacts.keys() != expected_paths:
        raise ValueError("Artifact manifest must match the approved evidence paths.")


def validate_reviews(payload: dict, plan) -> set[str]:
    reviews = payload["reviews"]
    inputs = payload["inputs"]
    if inputs is None or not isinstance(reviews, list) or len(reviews) != len(plan.routes):
        raise ValueError("Invalid review results for the configured routes.")
    builds = [attempt["browser_build"] for attempt in payload["attempts"]
              if attempt["engine"] == plan.engine and attempt["status"] == "completed"]
    paths = set()
    for route, review in zip(plan.routes, reviews, strict=True):
        record(review, "route_id path engine browser_build profile_sha256 visual accessibility", "route review")
        if (review["route_id"], review["path"], review["engine"]) != (route.id, route.path, plan.engine):
            raise ValueError("The review does not match its planned route and browser.")
        if review["profile_sha256"] != inputs["profile_sha256"]:
            raise ValueError("The review does not match the effective profile.")
        build = review["browser_build"]
        if build is not None and (len(builds) != 4 or any(build != item for item in builds)
                                  or build["platform"] != inputs["runner_platform"]):
            raise ValueError("The review does not match the observed browser build.")
        visual, accessibility = review["visual"], review["accessibility"]
        record(visual, "required status detail changed_pixels artifacts binding applied_approval", "visual review")
        record(accessibility, "required status detail axe_version findings", "accessibility review")
        for check, required, statuses in (
            (visual, route.visual_required, ("changed", "unchanged", "approved", "unavailable")),
            (accessibility, route.accessibility_required, ("regression", "passed", "unavailable")),
        ):
            if check["required"] is not required:
                raise ValueError("The review requirement does not match the profile.")
            enum(check["status"], statuses, "review check status")
            if check["status"] == "unavailable":
                string(check["detail"], "unavailable review detail")
            elif check["detail"] is not None or build is None:
                raise ValueError("An available review requires a browser build and has no execution error.")
            if check["required"] and payload["verdict"] == "VERIFIED" and check["status"] in (
                "changed", "regression", "unavailable",
            ):
                raise ValueError("An unresolved required review cannot be verified.")
        paths |= validate_visual(payload, plan.engine, route.id, build, visual)
        try:
            findings = findings_from_report(accessibility["findings"])
        except TypeError as error:
            raise ValueError("Invalid axe findings.") from error
        if len(findings) != len(accessibility["findings"]):
            raise ValueError("Duplicate axe findings.")
        if accessibility["status"] == "unavailable":
            if accessibility["axe_version"] is not None or findings:
                raise ValueError("An unavailable scan cannot report findings or an axe version.")
        else:
            string(accessibility["axe_version"], "axe version", AXE_VERSION)
            if bool(findings) != (accessibility["status"] == "regression"):
                raise ValueError("A regression requires newly detected findings.")
    return paths


def validate_visual(payload: dict, engine: str, route_id: str, build: dict, visual: dict) -> set[str]:
    status = visual["status"]
    changed = status in ("changed", "approved")
    binding = visual["binding"]
    approval = visual["applied_approval"]
    if (not changed and binding is not None) or (status != "approved" and approval is not None):
        raise ValueError("Visual binding and approval require changed pixels and the corresponding status.")
    if status == "unavailable":
        if visual["changed_pixels"] is not None or visual["artifacts"] != {}:
            raise ValueError("An unavailable visual comparison cannot report screenshot evidence.")
        return set()
    allowed = {role: f"review/{engine}/{route_id}/{name}" for role, name in REVIEW_FILES.items()}
    paths = validate_artifact_paths(visual["artifacts"], allowed, "review screenshot")
    if paths != set(allowed.values()):
        raise ValueError("An available visual comparison requires all three screenshot artifacts.")
    for path in paths:
        metadata = payload["artifacts"].get(path)
        if metadata is None or not 0 < metadata["size"] <= MAX_PNG_BYTES:
            raise ValueError("Review screenshot is missing or outside size limits.")
    inputs = payload["inputs"]
    settings = inputs["settings"]
    max_changed = settings["viewport_width"] * settings["viewport_height"] if changed else 0
    integer(visual["changed_pixels"], int(changed), max_changed, "changed pixels")
    if changed:
        expected = {"route_id": route_id, "engine": engine, "browser_build": build, "commit": payload["head_sha"],
                    "profile_sha256": inputs["profile_sha256"],
                    "screenshot_sha256": payload["artifacts"][allowed["head"]]["sha256"]}
        if binding != expected:
            raise ValueError("The visual approval binding does not match the screenshot and comparison inputs.")
    if status == "approved":
        record(approval, "binding run_id receipt_sha accepted_by accepted_at", "visual approval")
        string(approval["run_id"], "approval source run ID")
        string(approval["receipt_sha"], "approval source receipt SHA-256", SHA256)
        string(approval["accepted_at"], "approval timestamp")
        if (str(UUID(approval["run_id"])) != approval["run_id"]
            or approval["binding"] != binding or approval["accepted_by"] != "owner"
            or datetime.fromisoformat(approval["accepted_at"]).utcoffset() is None):
            raise ValueError("The recorded visual approval does not match the screenshot binding.")
    return paths
