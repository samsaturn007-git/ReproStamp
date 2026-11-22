"""Run the PRD-01 exit gates against real Git commits and Chromium containers."""

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = Path(sys.executable).parent / "bverify"
BASE = "checkout-base"
FIXED = "checkout-fixed"


@dataclass(frozen=True)
class Scenario:
    name: str
    base: str
    head: str
    code: int
    verdict: str
    reason: str
    state: str = "completed"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=BuildVerify Test", "-c", "user.email=test@buildverify.invalid",
         "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
    ).stdout.strip()


def make_variant(repo: Path, base: str, filename: str, edit) -> str:
    git(repo, "checkout", "--quiet", "--detach", base)
    path = repo / filename
    before = path.read_text(encoding="utf-8")
    after = edit(before)
    assert after != before, filename
    path.write_text(after, encoding="utf-8")
    git(repo, "add", "--", filename)
    git(repo, "commit", "-m", f"Test change to {filename}")
    return git(repo, "rev-parse", "HEAD")


def check_artifacts(output: Path, result: dict) -> None:
    for attempt in result["attempts"]:
        for case in attempt["cases"]:
            artifacts = case["artifacts"]
            if case["status"] == "assertion_failed":
                assert zipfile.is_zipfile(output / artifacts["trace"]), artifacts
                with (output / artifacts["screenshot"]).open("rb") as file:
                    assert file.read(8) == b"\x89PNG\r\n\x1a\n", artifacts


def compare(repo: Path, profiles: Path, outputs: Path, scenario: Scenario, profile: dict) -> dict:
    profile_file = profiles / f"{scenario.name}.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    out = outputs / scenario.name
    process = subprocess.run(
        [str(CLI), "compare", "--repo", str(repo), "--base", scenario.base, "--head", scenario.head,
         "--profile", str(profile_file), "--out", str(out)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=210,
    )
    assert process.returncode == scenario.code, process.stdout
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert (result["verdict"], result["reason"], result["execution_state"]) == (
        scenario.verdict, scenario.reason, scenario.state,
    ), process.stdout
    assert f"{scenario.verdict} [{scenario.reason}]" in process.stdout, process.stdout
    attempts = result["attempts"]
    if scenario.state == "blocked":
        assert not attempts, attempts
    else:
        assert [(item["side"], item["number"], item["engine"]) for item in attempts] == [
            (side, number, "chromium") for side in ("base", "head") for number in (1, 2)
        ], attempts
        assert all(item["duration_ms"] > 0 for item in attempts)
        check_artifacts(out, result)

    run_id = result["run_id"]
    containers = subprocess.check_output(
        ["docker", "ps", "-aq", "--filter", f"label=io.buildverify.run={run_id}"], text=True, timeout=15,
    )
    assert not containers.strip(), f"Still present: {containers}"
    assert not list(Path(tempfile.gettempdir()).glob(f"bverify-{run_id}-*")), "Temporary workspace leaked."
    print(f"PASS {scenario.name} ({scenario.code}) {scenario.verdict} [{scenario.reason}]", flush=True)
    return result


def main() -> None:
    original = json.loads((ROOT / "profiles/checkout.json").read_text(encoding="utf-8"))
    for key in ("repository", "harness", "npm_cache"):
        original[key] = str((ROOT / "profiles" / original[key]).resolve())
    outputs = Path(tempfile.mkdtemp(prefix="prd01-gates-", dir=ROOT / ".buildverify"))
    print(f"Evidence directory: {outputs}", flush=True)
    with tempfile.TemporaryDirectory(prefix="prd01-inputs-") as temp:
        inputs = Path(temp).resolve()
        repo = inputs / "checkout repo"
        subprocess.run(["git", "clone", "--quiet", "--no-local", original["repository"], str(repo)], check=True)
        profile = {**original, "repository": str(repo)}
        ineffective = make_variant(repo, BASE, "src/checkout.ts", lambda text: text.replace("1_000", "1000"))
        regressed = make_variant(repo, FIXED, "src/checkout.ts", lambda text: text.replace(
            ": subtotalInCents;", ": subtotalInCents + 500;",
        ))
        disallowed = make_variant(repo, FIXED, "package-lock.json", lambda text: text + "\n")
        git(repo, "checkout", "--quiet", "--detach", FIXED)
        (repo / "src/checkout.spec.cjs").write_text("// An app-owned test change.\n", encoding="utf-8")
        git(repo, "add", "src/checkout.spec.cjs")
        git(repo, "commit", "-m", "Change a protected test")
        test_change = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "--quiet", "--detach", FIXED)
        (repo / "src/link.ts").symlink_to("checkout.ts")
        git(repo, "add", "src/link.ts")
        git(repo, "commit", "-m", "Add unsupported symlink")
        symlink = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "--quiet", "--detach", FIXED)
        git(repo, "update-index", "--add", "--cacheinfo", f"160000,{symlink},src/gitlink")
        git(repo, "commit", "-m", "Add unsupported Git link")
        gitlink = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "--quiet", "--detach", FIXED)

        dirty_file = repo / "src/checkout.ts"
        dirty_file.write_text("uncommitted and invalid TypeScript {\n", encoding="utf-8")
        cases = [
            Scenario("known-good-fix", BASE, FIXED, 0, "VERIFIED", "expected_fix_confirmed"),
            Scenario("ineffective-edit", BASE, ineffective, 1, "FAILED", "candidate_assertion_failed"),
            Scenario("new-regression", BASE, regressed, 1, "FAILED", "candidate_regression"),
            Scenario("baseline-already-passes", FIXED, FIXED, 3, "INCONCLUSIVE", "baseline_not_reproduced"),
            Scenario("disallowed-lock-change", BASE, disallowed, 4, "POLICY_BLOCKED", "disallowed_change", "blocked"),
            Scenario("disallowed-test-change", BASE, test_change, 4, "POLICY_BLOCKED", "disallowed_change", "blocked"),
            Scenario("symlink", BASE, symlink, 4, "POLICY_BLOCKED", "unsupported_repository_entry", "blocked"),
            Scenario("submodule", BASE, gitlink, 4, "POLICY_BLOCKED", "unsupported_repository_entry", "blocked"),
        ]
        for scenario in cases:
            result = compare(repo, inputs, outputs, scenario, profile)
            if scenario.name == "known-good-fix":
                for attempt in result["attempts"]:
                    observed = {case["case_id"]: case for case in attempt["cases"]}
                    discount = observed["checkout.discount"]
                    assert observed["checkout.full-price"]["status"] == "passed"
                    if attempt["side"] == "base":
                        assert discount["assertion"] == {
                            "id": "discounted_total", "actual": "$110.00", "expected": "$90.00",
                        }
                    else:
                        assert discount["status"] == "passed"
                assert git(repo, "status", "--porcelain") == "M src/checkout.ts"

        missing_image = profile["runner_image"].split("@", 1)[0] + "@sha256:" + "0" * 64
        startup = Scenario("runner-startup", BASE, FIXED, 3, "INCONCLUSIVE", "runner_startup_failed", "incomplete")
        compare(repo, inputs, outputs, startup, {**profile, "runner_image": missing_image})

        slow = inputs / "slow-harness"
        shutil.copytree(profile["harness"], slow, ignore=shutil.ignore_patterns("node_modules"))
        readiness = slow / "wait-for-app.cjs"
        readiness.write_text(readiness.read_text(encoding="utf-8").replace(
            "        return;", "        await delay(60_000);\n        return;",
        ), encoding="utf-8")
        timeout = Scenario("timeout-and-cleanup", BASE, FIXED, 3, "INCONCLUSIVE", "attempt_timeout", "incomplete")
        result = compare(repo, inputs, outputs, timeout, {**profile, "harness": str(slow), "timeout_seconds": 8})
        assert all(attempt["reason"] == "attempt_timeout" for attempt in result["attempts"])
        for attempt in result["attempts"]:
            logs = outputs / timeout.name / attempt["logs"]["harness"]
            assert "BuildVerify app is ready" in logs.read_text(encoding="utf-8"), logs
        print("PASS all four timeout workloads reached app readiness before being removed", flush=True)

    print(f"PRD-01 exit gates passed. Evidence: {outputs}")


if __name__ == "__main__":
    main()
