import argparse
import json
import subprocess
import sys
import tempfile
import uuid
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from .profile import PolicyError, load_profile
from .receipt import browser_builds, export_receipt, matrix, verify_bundle
from .repository import Repository, RepositoryError, changed_paths
from .run_inputs import fingerprint_inputs, run_plan
from .runner import Attempt, DockerError, freeze_harness, run_attempt, runner_platform
from .verdict import EXIT_CODES, Verdict, classify


class ReplayError(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


class ComparisonInterrupted(KeyboardInterrupt):
    """Stop a worker-owned comparison without publishing a receipt."""


BUNDLE_ERRORS = (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile, zlib.error)


def print_attempt(attempt: Attempt) -> None:
    print(f"{attempt.side} attempt {attempt.number} [{attempt.engine}] {attempt.status} ({attempt.duration_ms} ms)", flush=True)
    for case in attempt.cases:
        assertion = f" [{case.assertion.id} received {case.assertion.actual!r}]" if case.assertion else ""
        print(f"  {case.case_id} {case.status}{assertion}")
        for path in case.artifacts.values():
            print(f"    {path}")
    if attempt.reason:
        print(f"  {attempt.reason}")


def compare(
    args: argparse.Namespace, original: dict | None = None, *, run_id: str | None = None,
    workspace_parent: Path | None = None,
    on_attempt_start: Callable[[str, str, int], None] | None = None,
    on_attempt: Callable[[Attempt], None] | None = None,
) -> int:
    profile = input_error = None
    try:
        repo_path = Path(args.repo).resolve(strict=True)
        profile_path = Path(args.profile).resolve()
        profile = load_profile(profile_path, repo_path)
    except (PolicyError, OSError, RuntimeError) as error:
        input_error = error
    try:
        out = Path(args.out).resolve()
        protected = [Path(args.repo).resolve()]
        if profile:
            protected += [profile.harness, profile.npm_cache]
        if any(out.is_relative_to(path) for path in protected):
            raise ValueError("Keep --out outside the repository, harness, and dependency cache.")
        out.mkdir(mode=0o700, parents=True, exist_ok=False)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"reprostamp: --out must be a new directory ({error})", file=sys.stderr)
        return 2

    run_id = run_id or uuid.uuid4().hex
    attempts = []
    engine_verdicts = {}
    result = {
        "schema_version": 1, "run_id": run_id, "repository": args.repo,
        "profile": args.profile, "base_ref": args.base, "head_ref": args.head,
        "base_sha": None, "head_sha": None, "runner_image": None,
        "plan": run_plan(profile) if profile else {"engines": [], "case_ids": []},
        "inputs": None, "replay_of": original["payload_sha256"] if original else None,
    }
    try:
        if input_error is not None:
            raise input_error
        result.update(repository=str(repo_path), profile=str(profile_path), runner_image=profile.runner_image)
        repo = Repository(repo_path)
        base = result["base_sha"] = repo.resolve(args.base)
        head = result["head_sha"] = repo.resolve(args.head)
        base_entries, head_entries = repo.tree(base), repo.tree(head)
        result["changed_paths"] = changed_paths(base_entries, head_entries, profile)

        with tempfile.TemporaryDirectory(prefix=f"reprostamp-{run_id}-", dir=workspace_parent) as temp:
            workspace = Path(temp).resolve()
            harness = workspace / "harness"
            freeze_harness(profile.harness, harness)
            platform = None
            image_error = None
            try:
                platform = runner_platform(profile.runner_image)
            except (DockerError, subprocess.TimeoutExpired) as error:
                image_error = error
            result["inputs"] = fingerprint_inputs(
                repo, profile, harness, base, base_entries, head_entries, result["changed_paths"], platform,
            )
            if original:
                match_replay(original["payload"], result, image_error)

            print(f"Comparing {base} → {head}", flush=True)
            for side, entries in (("base", base_entries), ("head", head_entries)):
                repo.export(entries, workspace / side)
            for engine in profile.engines:
                for side, sha in (("base", base), ("head", head)):
                    for number in (1, 2):
                        if on_attempt_start:
                            on_attempt_start(engine, side, number)
                        attempt = run_attempt(
                            profile, run_id=run_id, side=side, number=number, commit=sha, engine=engine,
                            app=workspace / side, harness=harness, work_root=workspace, out_root=out,
                        )
                        attempts.append(attempt)
                        if on_attempt:
                            on_attempt(attempt)
                        print_attempt(attempt)
        verdict, engine_verdicts = classify(profile, attempts, platform)
        execution_state = "completed" if all(attempt.status == "completed" for attempt in attempts) else "incomplete"
    except PolicyError as error:
        execution_state = "blocked"
        verdict = Verdict("POLICY_BLOCKED", error.reason, str(error))
    except ReplayError as error:
        execution_state = "incomplete"
        verdict = Verdict("INCONCLUSIVE", error.reason, str(error))
    except (RepositoryError, OSError, RuntimeError, ValueError) as error:
        execution_state = "incomplete"
        verdict = Verdict("INCONCLUSIVE", "input_unavailable", str(error))
    except ComparisonInterrupted:
        raise
    except KeyboardInterrupt:
        execution_state = "incomplete"
        verdict = Verdict("INCONCLUSIVE", "interrupted", "The operator interrupted the comparison.")

    result.update(
        execution_state=execution_state, verdict=verdict.name, reason=verdict.reason,
        detail=verdict.detail, attempts=[asdict(attempt) for attempt in attempts],
        engine_verdicts={engine: asdict(item) for engine, item in engine_verdicts.items()},
    )
    if original and execution_state == "completed":
        observed = browser_builds(result)
        prior = browser_builds(original["payload"])
        changed = [engine for engine, builds in prior.items() if builds and builds != observed.get(engine)]
        if changed:
            verdict = Verdict("INCONCLUSIVE", "replay_browser_build_changed", f"Observed builds changed for {', '.join(changed)}.")
            result.update(verdict=verdict.name, reason=verdict.reason, detail=verdict.detail)
    try:
        pending = out / ".result.json.tmp"
        pending.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        pending.replace(out / "result.json")
    except OSError as error:
        print(f"INCONCLUSIVE [result_write_failed] {error}", file=sys.stderr)
        return EXIT_CODES["INCONCLUSIVE"]
    try:
        receipt = export_receipt(out, result)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"INCONCLUSIVE [receipt_write_failed] {error}", file=sys.stderr)
        return EXIT_CODES["INCONCLUSIVE"]
    print(f"{verdict.name} [{verdict.reason}] {verdict.detail}")
    print(f"Evidence: {out / 'result.json'}")
    print(f"Receipt {receipt['payload_sha256']}: {out / 'receipt.zip'}")
    return EXIT_CODES[verdict.name]


CONTROLS = {
    "repository_sha256": "repository identity", "oracle_sha256": "oracle", "runner_image": "pinned image",
    "runner_platform": "runner platform", "runner_contract": "runner contract", "settings": "run settings",
    "profile_sha256": "profile", "lockfile_sha256": "dependency lockfiles",
}


def match_replay(prior: dict, current: dict, image_error: Exception | None) -> None:
    expected, actual = prior["inputs"], current["inputs"]
    for key in (*CONTROLS, "diff_sha256"):
        if key != "runner_platform" and expected[key] != actual[key]:
            label = CONTROLS.get(key, "commit diff")
            raise ReplayError(f"replay_{key.removesuffix('_sha256')}_changed", f"The {label} differs from the original receipt.")
    if prior["plan"] != current["plan"] or any(prior[f"{side}_sha"] != current[f"{side}_sha"] for side in ("base", "head")):
        raise ReplayError("replay_plan_changed", "The requested matrix or immutable commits differ from the original receipt.")
    if image_error:
        raise ReplayError("replay_image_unavailable", f"Pinned image {actual['runner_image']} is unavailable locally. {image_error}")
    if expected["runner_platform"] is not None and expected["runner_platform"] != actual["runner_platform"]:
        raise ReplayError("replay_runner_platform_changed", f"Expected {expected['runner_platform']}, found {actual['runner_platform']}.")


def replay(args: argparse.Namespace) -> int:
    original = verify_bundle(Path(args.bundle))
    payload = original["payload"]
    if payload["inputs"] is None:
        print("INCONCLUSIVE [replay_inputs_missing] The receipt does not contain the required run inputs.", file=sys.stderr)
        return EXIT_CODES["INCONCLUSIVE"]
    args.base, args.head = payload["base_sha"], payload["head_sha"]
    return compare(args, original)


def verify(args: argparse.Namespace) -> int:
    receipt = verify_bundle(Path(args.bundle))
    print(f"Integrity verified: {receipt['payload_sha256']} ({len(receipt['payload']['artifacts'])} files)")
    print(f"Recorded verdict: {receipt['payload']['verdict']} [{receipt['payload']['reason']}]")
    return 0


def cell_outcome(cell: dict | None) -> str:
    if cell is None:
        return "outside plan"
    status = cell["status"]
    if assertion := cell["assertion"]:
        status += f" ({assertion['id']!r}: {assertion['actual']!r}, expected {assertion['expected']!r})"
    if cell["attempt_reason"]:
        status += f" [{cell['attempt_reason']}]"
    return status


def diff_receipts(args: argparse.Namespace) -> int:
    left, right = (verify_bundle(Path(path))["payload"] for path in (args.left, args.right))
    print(f"Verdict: {left['verdict']} [{left['reason']}] → {right['verdict']} [{right['reason']}]")
    barriers = []
    if not left["inputs"] or not right["inputs"]:
        barriers.append("run inputs missing")
    else:
        barriers.extend(label for key, label in CONTROLS.items() if left["inputs"][key] != right["inputs"][key])
        if left["inputs"]["runner_platform"] is None or right["inputs"]["runner_platform"] is None:
            barriers.append("runner platform missing")
        if not barriers and left["inputs"]["diff_sha256"] != right["inputs"]["diff_sha256"]:
            print("Commit diff changed.")
    if left["base_sha"] != right["base_sha"]:
        barriers.append("base commit changed")
    if left["head_sha"] != right["head_sha"]:
        print(f"Candidate commit: {left['head_sha']} → {right['head_sha']}")
    if left["plan"] != right["plan"]:
        barriers.append("required browser or case plan changed")
    left_builds, right_builds = browser_builds(left), browser_builds(right)
    for engine in sorted(left_builds.keys() | right_builds.keys()):
        if not left_builds.get(engine) or not right_builds.get(engine):
            barriers.append(f"{engine} build evidence missing")
        elif left_builds[engine] != right_builds[engine] or len(left_builds[engine]) != 1:
            barriers.append(f"{engine} builds differ")
    left_cells, right_cells = matrix(left), matrix(right)
    if any(case["status"] in ("missing", "unsupported", "error") for case in (*left_cells.values(), *right_cells.values())):
        barriers.append("required assertion evidence missing or unsupported")
    if any(receipt["execution_state"] != "completed" for receipt in (left, right)):
        barriers.append("execution incomplete")
    if barriers:
        print("Inputs prevent a fair comparison: " + ", ".join(barriers))
    else:
        print("Comparison inputs match.")
    changed = 0
    for key in sorted(left_cells.keys() | right_cells.keys()):
        before, after = cell_outcome(left_cells.get(key)), cell_outcome(right_cells.get(key))
        if before != after:
            engine, case, side, attempt = key
            print(f"{engine} {case} {side} attempt {attempt}: {before} → {after}")
            changed += 1
    if not changed:
        print("No case outcomes changed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reprostamp", description="Compare commits using independent browser tests.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("compare", help="verify a candidate commit against a base commit")
    command.add_argument("--repo", required=True, help="approved local Git checkout")
    command.add_argument("--base", required=True, help="base Git ref or commit SHA")
    command.add_argument("--head", required=True, help="candidate Git ref or commit SHA")
    command.set_defaults(handler=compare)
    replay_command = commands.add_parser("replay", help="rerun the local inputs from an intact receipt bundle")
    replay_command.add_argument("bundle", help="receipt ZIP path")
    replay_command.add_argument("--repo", required=True, help="approved local Git checkout")
    replay_command.set_defaults(handler=replay)
    for item in (command, replay_command):
        item.add_argument("--profile", required=True, help="owner-managed JSON profile outside the checkout")
        item.add_argument("--out", required=True, help="new directory for results and evidence")
    verify_command = commands.add_parser("verify", help="check a receipt bundle offline")
    verify_command.add_argument("bundle", help="receipt ZIP path")
    verify_command.set_defaults(handler=verify)
    diff_command = commands.add_parser("diff-receipts", help="compare case outcomes and run inputs offline")
    diff_command.add_argument("left", help="first receipt ZIP path")
    diff_command.add_argument("right", help="second receipt ZIP path")
    diff_command.set_defaults(handler=diff_receipts)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except BUNDLE_ERRORS as error:
        print(f"reprostamp: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
