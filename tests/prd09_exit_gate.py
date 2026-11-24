"""Exercise app export, policy, adaptive context, and the paired golden evaluation."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from reprostamp.app_context import RepoMap
from reprostamp.app_source import APP_FILES, EDITABLE_FILES, MANIFEST
from reprostamp.receipt import verify_bundle
from reprostamp.starter import validate_receipt
from reprostamp.starter_runner import APP_CASE_IDS, ENGINES, TEMPLATE

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/app"


def invoke(*args, expected=0, message=""):
    command = [sys.executable, "-m", "reprostamp.cli", *map(str, args)]
    env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=600)
    assert result.returncode == expected and message in result.stdout + result.stderr, result.stdout + result.stderr
    return result.stdout


def check_context(output):
    source = output / "index-fixture"
    (source / "src").mkdir(parents=True)
    for name in EDITABLE_FILES:
        shutil.copyfile(TEMPLATE / name, source / name)
    index = RepoMap()
    assert index.refresh(source) == len(EDITABLE_FILES)
    assert index.refresh(source) == 0
    original = index.entries.copy()
    css = source / "src/style.css"
    with css.open("a", encoding="utf-8") as stylesheet:
        stylesheet.write("\n/* palette diagnostic marker */\n")
    assert index.refresh(source) == 1
    assert index.entries["src/style.css"].sha256 != original["src/style.css"].sha256
    assert index.entries["main.py"] is original["main.py"]
    _, metrics = index.context("Validate TaskInput normalization", failure="src/style.css palette diagnostic marker")
    assert metrics["selected_paths"][0] == "src/style.css"
    assert metrics["selected_context_bytes"] < metrics["full_context_bytes"]


def check_blocking(output, cache):
    patch = json.loads((EXAMPLES / "field-notes.json").read_bytes())
    invalid = output / "invalid.json"
    bad_out = output / "blocked"
    for overrides, message in [
        ({"stack": "go"}, "Unsupported app"),
        ({"scripts": {"preinstall": "arbitrary-script"}}, "requires only stack, config, and presentation"),
        ({"files": {"../README.md": "arbitrary-path"}}, "requires only stack, config, and presentation"),
        ({"presentation": {**patch["presentation"], "palette": "url(unsupported)"}}, "forest, ocean, or plum"),
    ]:
        invalid.write_text(json.dumps({**patch, **overrides}), encoding="utf-8")
        invoke("app", "generate", "--plan", invalid, "--cache", cache, "--out", bad_out, expected=2, message=message)
        assert not bad_out.exists()
    command = ("app", "generate", "--requirements", EXAMPLES / "field-notes.txt", "--ollama-model", "unused",
               "--cache", cache, "--out", bad_out)
    preview = json.loads(invoke(*command))
    assert preview["experimental"] and not bad_out.exists()
    invoke(*command, "--approve", "0" * 64, expected=2, message="approval_mismatch")
    assert not bad_out.exists()


def receipt(directory, *, result="passed"):
    payload = verify_bundle(directory / "receipt.zip", validate=validate_receipt)["payload"]
    assert payload["result"] == result
    assert payload["template"] == "task-tracker/v2"
    assert payload["checks"] == list(APP_CASE_IDS)
    assert [run["engine"] for run in payload["runs"]] == list(ENGINES)
    for run in payload["runs"]:
        assert run["execution_state"] == "completed"
        assert len(run["checks"]) == len(APP_CASE_IDS)
        assert "Ran 3 tests" in (directory / run["logs"]["app"]).read_text()
    return payload


def check_benchmark(directory):
    report = json.loads((directory / "report.json").read_bytes())
    assert report["n"] == 2
    assert report["summary"]["single"]["passed"] == 1
    assert report["summary"]["plan-review"]["passed"] == 2
    assert report["summary"]["single"]["model_calls"] == 2
    assert report["summary"]["plan-review"]["model_calls"] == 6
    assert report["summary"]["single"]["input_tokens"] is None
    assert report["index"]["files_reparsed_without_changes"] == 0
    for trial in report["trials"]:
        assert trial["wall_ms"] > 0
        run = directory / trial["fixture"] / trial["arm"]
        payload = receipt(run, result=trial["result"])
        assert payload["harness_sha256"] == report["harness_sha256"]
        if trial["result"] == "failed":
            assert trial["fixture"] == "studio-requests" and trial["arm"] == "single"
            assert payload["oracle_plan_sha256"] != payload["app_plan_sha256"]
            for outcome in trial["checks"]:
                assert outcome["checks"]["browser.presentation"] == "assertion_failed"
        else:
            assert payload["oracle_plan_sha256"] == payload["app_plan_sha256"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, help="reuse a completed golden benchmark for verification")
    args = parser.parse_args()
    cache = args.cache.resolve()
    (ROOT / ".reprostamp").mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="prd09-gates-", dir=ROOT / ".reprostamp"))
    print(f"Evidence directory: {output}", flush=True)
    check_context(output)
    check_blocking(output, cache)

    benchmark = args.benchmark.resolve() if args.benchmark else output / "benchmark"
    if args.benchmark is None:
        print(invoke("app", "benchmark", "--suite", EXAMPLES / "evaluation.json", "--cache", cache, "--out", benchmark),
              end="", flush=True)
    check_benchmark(benchmark)
    generated = output / "generated"
    print(invoke("app", "generate", "--plan", EXAMPLES / "field-notes.json", "--cache", cache, "--out", generated),
          end="", flush=True)
    first = receipt(generated)
    assert first["artifacts"]["source.zip"] == receipt(benchmark / "field-notes/single")["artifacts"]["source.zip"]
    extracted = output / "extracted"
    with zipfile.ZipFile(generated / "source.zip") as archive:
        assert set(archive.namelist()) == set(APP_FILES)
        assert json.loads(archive.read("app-manifest.json")) == MANIFEST
        archive.extractall(extracted)

    blocked = output / "edited"
    package = extracted / "package.json"
    original = package.read_bytes()
    package.write_bytes(original + b"\n")
    command = ("app", "validate", "--source", extracted, "--cache", cache, "--out", blocked)
    invoke(*command, expected=2, message="differs from the reproducible export")
    assert not blocked.exists()
    package.write_bytes(original)
    stylesheet = extracted / "src/style.css"
    unrelated = output / "unrelated.css"
    stylesheet.rename(unrelated)
    stylesheet.symlink_to(unrelated)
    invoke(*command, expected=2, message="must be a regular file")
    assert not blocked.exists()
    stylesheet.unlink()
    unrelated.rename(stylesheet)

    revalidated = output / "revalidated"
    print(invoke("app", "validate", "--source", extracted, "--cache", cache, "--out", revalidated), end="", flush=True)
    other = receipt(revalidated)
    assert other["origin"] == "revalidation"
    assert first["artifacts"]["source.zip"] == other["artifacts"]["source.zip"]
    print("PASS reproducible export, independent paired oracle, context, approval, and runner policy", flush=True)


if __name__ == "__main__":
    main()
