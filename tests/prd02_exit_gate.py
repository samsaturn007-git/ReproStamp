"""Exercise the PRD-02 matrix, offline receipt commands, and replay on owned fixtures."""

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from reprostamp.integrity import hash_json


ROOT = Path(__file__).resolve().parents[1]
CLI = Path(sys.executable).parent / "reprostamp"
ENGINES = {"chromium", "firefox", "webkit"}


def invoke(*args: str, code: int = 0, contains: str) -> str:
    result = subprocess.run(
        [str(CLI), *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, timeout=360,
    )
    assert result.returncode == code and contains in result.stdout, result.stdout
    return result.stdout


def profile_args(profile: Path, out: Path) -> list[str]:
    settings = json.loads(profile.read_text(encoding="utf-8"))
    repo = profile.parent / settings["repository"]
    return ["--repo", str(repo), "--profile", str(profile), "--out", str(out)]


def result_at(out: Path) -> dict:
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    containers = subprocess.check_output(
        ["docker", "ps", "-aq", "--filter", f"label=io.reprostamp.run={result['run_id']}"], text=True, timeout=15,
    )
    assert not containers.strip(), containers
    assert not list(Path(tempfile.gettempdir()).glob(f"reprostamp-{result['run_id']}-*"))
    return result


def check_matrix(out: Path, fixture: str) -> Path:
    result = result_at(out)
    attempts = result["attempts"]
    assert result["execution_state"] == "completed" and result["verdict"] == "VERIFIED", result
    assert {(a["engine"], a["side"], a["number"]) for a in attempts} == {
        (engine, side, number) for engine in ENGINES for side in ("base", "head") for number in (1, 2)
    }
    assert len(attempts) == 12
    expected = "checkout.discount" if fixture == "checkout" else "shipping.free-at-threshold"
    for attempt in attempts:
        assert attempt["browser_build"]["version"]
        assert attempt["browser_build"]["platform"] == result["inputs"]["runner_platform"]
        assert len(attempt["cases"]) == 2
        for case in attempt["cases"]:
            if case["case_id"] == expected and attempt["side"] == "base":
                assert case["status"] == "assertion_failed", case
                assert zipfile.is_zipfile(out / case["artifacts"]["trace"]), case
                with (out / case["artifacts"]["screenshot"]).open("rb") as screenshot:
                    assert screenshot.read(8) == b"\x89PNG\r\n\x1a\n", case
            else:
                assert case["status"] == "passed", case
    bundle = out / "receipt.zip"
    invoke("verify", str(bundle), contains="Recorded verdict: VERIFIED")
    with zipfile.ZipFile(bundle) as archive:
        for name in ("receipt.json", "receipt.md"):
            assert archive.read(name) == (out / name).read_bytes()
    return bundle


def mutate_bundles(original: Path, out: Path) -> None:
    with zipfile.ZipFile(original) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    receipt = json.loads(members["receipt.json"])
    receipt["payload"]["verdict"] = "FAILED"
    trace = next(name for name in members if name.endswith("/trace.zip"))
    replaced = bytes([members[trace][0] ^ 1]) + members[trace][1:]
    invalid_schema = json.loads(members["receipt.json"])
    invalid_schema["payload"]["attempts"][0]["number"] = 5
    invalid_schema["payload_sha256"] = hash_json(invalid_schema["payload"])
    scenarios = (
        ("modified-receipt", {**members, "receipt.json": json.dumps(receipt)}, "Receipt payload SHA-256 mismatch"),
        ("replaced-trace", {**members, trace: replaced}, "Artifact SHA-256 mismatch"),
        ("missing-artifact", {name: data for name, data in members.items() if name != trace}, "Missing artifact"),
        ("unsafe-member", {**members, "../trace.zip": b"unsafe archive entry"}, "Unsafe or duplicate bundle member"),
        ("invalid-schema", {**members, "receipt.json": json.dumps(invalid_schema)}, "Invalid attempt number"),
    )
    for name, files, expected in scenarios:
        path = out / f"{name}.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, data in files.items():
                archive.writestr(filename, data)
        invoke("verify", str(path), code=2, contains=expected)
        print(f"PASS offline {name}", flush=True)


def main() -> None:
    outputs = Path(tempfile.mkdtemp(prefix="prd02-gates-", dir=ROOT / ".reprostamp"))
    print(f"Evidence directory: {outputs}", flush=True)
    for fixture in ("checkout", "shipping"):
        profile = ROOT / "profiles" / f"{fixture}.json"
        output = outputs / fixture
        invoke("compare", "--base", f"{fixture}-base", "--head", f"{fixture}-fixed",
               *profile_args(profile, output), contains="VERIFIED [expected_fix_confirmed]")
        check_matrix(output, fixture)
        print(f"PASS {fixture} matrix (12 attempts, 24 cases)", flush=True)

    original = outputs / "checkout" / "receipt.zip"
    mutate_bundles(original, outputs)
    profile_path = ROOT / "profiles" / "checkout.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    for key in ("repository", "harness", "npm_cache"):
        profile[key] = str((profile_path.parent / profile[key]).resolve())
    with tempfile.TemporaryDirectory(prefix="prd02-inputs-") as temp:
        inputs = Path(temp)
        repo = inputs / "app"
        subprocess.run(["git", "clone", "--quiet", "--no-local", profile["repository"], str(repo)], check=True)
        harness = inputs / "harness"
        shutil.copytree(profile["harness"], harness, ignore=shutil.ignore_patterns("node_modules"))
        profile.update(repository="app", harness="harness")
        independent_profile = inputs / "checkout.json"
        independent_profile.write_text(json.dumps(profile), encoding="utf-8")

        replay_out = outputs / "replayed"
        invoke("replay", str(original), *profile_args(independent_profile, replay_out),
               contains="VERIFIED [expected_fix_confirmed]")
        replayed = check_matrix(replay_out, "checkout")
        prior = json.loads((original.parent / "receipt.json").read_text(encoding="utf-8"))
        successor = json.loads((replay_out / "receipt.json").read_text(encoding="utf-8"))
        assert successor["payload"]["replay_of"] == prior["payload_sha256"]
        assert successor["payload"]["run_id"] != prior["payload"]["run_id"]
        diff = invoke("diff-receipts", str(original), str(replayed), contains="No case outcomes changed.")
        assert "Comparison inputs match." in diff, diff
        print("PASS replay from independent checkout and matching receipt diff", flush=True)

        ineffective = outputs / "ineffective"
        invoke("compare", "--base", "checkout-base", "--head", "checkout-base",
               *profile_args(independent_profile, ineffective), code=1, contains="FAILED [candidate_assertion_failed]")
        diff = invoke("diff-receipts", str(original), str(ineffective / "receipt.zip"),
                      contains="webkit checkout.discount head attempt 2: passed → assertion_failed")
        assert "Comparison inputs match." in diff and "Candidate commit:" in diff, diff
        print("PASS outcome diff for a repeatable candidate failure", flush=True)

        spec = harness / "checkout.spec.cjs"
        source = spec.read_text(encoding="utf-8")
        spec.write_text(source + "\n// changed oracle\n", encoding="utf-8")
        changed = outputs / "changed-oracle"
        invoke("replay", str(original), *profile_args(independent_profile, changed), code=3,
               contains="[replay_oracle_changed]")
        assert result_at(changed)["attempts"] == []
        invoke("diff-receipts", str(original), str(changed / "receipt.zip"), contains="prevent a fair comparison: oracle")
        print("PASS changed oracle rejected before execution", flush=True)

        profile["engines"] = ["firefox"]
        independent_profile.write_text(json.dumps(profile), encoding="utf-8")
        spec.write_text(source.replace("test('checkout.full-price'", "test.skip('checkout.full-price'"), encoding="utf-8")
        missing = outputs / "missing-required-case"
        invoke("compare", "--base", "checkout-base", "--head", "checkout-fixed",
               *profile_args(independent_profile, missing), code=3, contains="[required_cell_missing]")
        assert {a["reason"] for a in result_at(missing)["attempts"]} == {"required_cell_missing"}
        assert "missing (" in (missing / "receipt.md").read_text(encoding="utf-8")
        invoke("verify", str(missing / "receipt.zip"), contains="Recorded verdict: INCONCLUSIVE")
        print("PASS missing required cell produces an inconclusive receipt", flush=True)

        spec.write_text(source, encoding="utf-8")
        config = harness / "playwright.config.cjs"
        original_config = config.read_text(encoding="utf-8")
        config.write_text(original_config.replace(
            "    headless: true,",
            "    launchOptions: { executablePath: '/missing-reprostamp-browser' },\n    headless: true,",
        ), encoding="utf-8")
        unsupported = outputs / "unsupported-engine"
        invoke("compare", "--base", "checkout-base", "--head", "checkout-fixed",
               *profile_args(independent_profile, unsupported), code=3, contains="[required_engine_unsupported]")
        assert {a["reason"] for a in result_at(unsupported)["attempts"]} == {"required_engine_unsupported"}
        assert "unsupported (" in (unsupported / "receipt.md").read_text(encoding="utf-8")
        invoke("verify", str(unsupported / "receipt.zip"), contains="Recorded verdict: INCONCLUSIVE")
        config.write_text(original_config, encoding="utf-8")
        print("PASS unavailable browser executable labels the required engine unsupported", flush=True)

        locked_image = profile["runner_image"]
        profile["runner_image"] = locked_image.split("@", 1)[0] + "@sha256:" + "0" * 64
        independent_profile.write_text(json.dumps(profile), encoding="utf-8")
        unavailable = outputs / "missing-image-source"
        invoke("compare", "--base", "checkout-base", "--head", "checkout-fixed",
               *profile_args(independent_profile, unavailable), code=3, contains="[runner_startup_failed]")
        image_replay = outputs / "missing-image-replay"
        invoke("replay", str(unavailable / "receipt.zip"), *profile_args(independent_profile, image_replay),
               code=3, contains="[replay_image_unavailable]")
        assert result_at(image_replay)["attempts"] == []
        print("PASS unavailable pinned image rejected before replay", flush=True)

    print(f"PRD-02 exit gates passed. Evidence: {outputs}")


if __name__ == "__main__":
    main()
