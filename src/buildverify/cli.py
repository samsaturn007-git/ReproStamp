import argparse
import json
import sys
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from .profile import PolicyError, load_profile
from .repository import Repository, RepositoryError, changed_paths
from .runner import Attempt, freeze_harness, run_attempt
from .verdict import EXIT_CODES, Verdict, classify


def print_attempt(attempt: Attempt) -> None:
    print(f"{attempt.side} attempt {attempt.number} [{attempt.engine}] {attempt.status} ({attempt.duration_ms} ms)", flush=True)
    for case in attempt.cases:
        assertion = f" [{case.assertion.id} received {case.assertion.actual!r}]" if case.assertion else ""
        print(f"  {case.case_id} {case.status}{assertion}")
        for path in case.artifacts.values():
            print(f"    {path}")
    if attempt.reason:
        print(f"  {attempt.reason}")


def compare(args: argparse.Namespace) -> int:
    try:
        out = Path(args.out).absolute()
        out.mkdir(mode=0o700, parents=True, exist_ok=False)
        out = out.resolve()
    except (OSError, RuntimeError) as error:
        print(f"bverify: --out must be a new directory ({error})", file=sys.stderr)
        return 2

    run_id = uuid.uuid4().hex
    attempts = []
    result = {
        "schema_version": 1, "run_id": run_id, "repository": args.repo,
        "profile": args.profile, "base_ref": args.base, "head_ref": args.head,
        "base_sha": None, "head_sha": None, "runner_image": None,
    }
    try:
        repo_path = Path(args.repo).resolve(strict=True)
        profile_path = Path(args.profile).resolve()
        profile = load_profile(profile_path, repo_path)
        result.update(repository=str(repo_path), profile=str(profile_path), runner_image=profile.runner_image)
        repo = Repository(repo_path)
        base = result["base_sha"] = repo.resolve(args.base)
        head = result["head_sha"] = repo.resolve(args.head)
        base_entries, head_entries = repo.tree(base), repo.tree(head)
        result["changed_paths"] = changed_paths(base_entries, head_entries, profile)

        print(f"Comparing {base} → {head}", flush=True)
        with tempfile.TemporaryDirectory(prefix=f"bverify-{run_id}-") as temp:
            workspace = Path(temp).resolve()
            harness = workspace / "harness"
            freeze_harness(profile.harness, harness)
            for side, sha, entries in (("base", base, base_entries), ("head", head, head_entries)):
                app = workspace / side
                repo.export(entries, app)
                for number in (1, 2):
                    attempt = run_attempt(
                        profile, run_id=run_id, side=side, number=number, commit=sha,
                        app=app, harness=harness, work_root=workspace, out_root=out,
                    )
                    attempts.append(attempt)
                    print_attempt(attempt)
        verdict = classify(profile, attempts)
        execution_state = "completed" if all(attempt.status == "completed" for attempt in attempts) else "incomplete"
    except PolicyError as error:
        execution_state = "blocked"
        verdict = Verdict("POLICY_BLOCKED", error.reason, str(error))
    except (RepositoryError, OSError, RuntimeError) as error:
        execution_state = "incomplete"
        verdict = Verdict("INCONCLUSIVE", "input_unavailable", str(error))
    except KeyboardInterrupt:
        execution_state = "incomplete"
        verdict = Verdict("INCONCLUSIVE", "interrupted", "The operator interrupted the comparison.")

    result.update(
        execution_state=execution_state, verdict=verdict.name, reason=verdict.reason,
        detail=verdict.detail, attempts=[asdict(attempt) for attempt in attempts],
    )
    try:
        pending = out / ".result.json.tmp"
        pending.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        pending.replace(out / "result.json")
    except OSError as error:
        print(f"INCONCLUSIVE [result_write_failed] {error}", file=sys.stderr)
        return EXIT_CODES["INCONCLUSIVE"]
    print(f"{verdict.name} [{verdict.reason}] {verdict.detail}")
    print(f"Evidence: {out / 'result.json'}")
    return EXIT_CODES[verdict.name]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bverify", description="Compare commits using independent browser tests.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("compare", help="verify a candidate commit against a base commit")
    command.add_argument("--repo", required=True, help="approved local Git checkout")
    command.add_argument("--base", required=True, help="base Git ref or commit SHA")
    command.add_argument("--head", required=True, help="candidate Git ref or commit SHA")
    command.add_argument("--profile", required=True, help="owner-managed JSON profile outside the checkout")
    command.add_argument("--out", required=True, help="new directory for results and evidence")
    args = parser.parse_args(argv)
    return compare(args)


if __name__ == "__main__":
    sys.exit(main())
