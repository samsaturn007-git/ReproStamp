"""Exercise the starter export, model approval, independent acceptance, and receipt integrity."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from reprostamp.integrity import hash_file
from reprostamp.receipt import verify_bundle
from reprostamp.starter import validate_receipt
from reprostamp.starter_runner import CASE_IDS, ENGINES


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/starter"


def invoke(*args, expected=0, message=""):
    env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
    run = subprocess.run([sys.executable, "-m", "reprostamp.cli", "starter", *map(str, args)], cwd=ROOT, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=750)
    assert run.returncode == expected and message in run.stdout, run.stdout
    return run.stdout


def check_export(output, config):
    bundle = verify_bundle(output / "receipt.zip", validate=validate_receipt)
    payload = bundle["payload"]
    assert payload["kind"] == "starter_validation" and payload["result"] == "passed"
    assert [run["engine"] for run in payload["runs"]] == list(ENGINES)
    for run in payload["runs"]:
        assert run["execution_state"] == "completed" and run["browser_build"]["version"]
        assert run["browser_build"]["platform"] == payload["runner_platform"]
        assert {check["case_id"]: check["status"] for check in run["checks"]} == dict.fromkeys(CASE_IDS, "passed")
    with (output / "source.zip").open("rb") as source:
        assert hash_file(source) == payload["artifacts"]["source.zip"]["sha256"]
    with zipfile.ZipFile(output / "source.zip") as archive:
        assert json.loads(archive.read("starter.json")) == json.loads(config.read_bytes())
        assert {"README.md", "package-lock.json", "requirements.lock"} <= set(archive.namelist())
        assert all("harness" not in name and ".spec." not in name for name in archive.namelist())
    invoke("verify", output / "receipt.zip", message="Recorded starter validation: passed")
    return payload


def test_invalid(output, cache):
    malformed = output / "invalid.json"
    malformed.write_text('{"project_name":"Bad", "task_fields": ["shell"], "statuses": ["Todo", "Done"]}')
    no_output = output / "invalid"
    invoke("generate", "--config", malformed, "--cache", cache, "--out", no_output, expected=2,
           message="task_fields must be a list drawn from")
    assert not no_output.exists()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock-only", action="store_true", help="run the checked-in deterministic model example")
    parser.add_argument("--cache", type=Path, help="reuse an already provisioned starter cache")
    args = parser.parse_args()
    (ROOT / ".reprostamp").mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="prd08-gates-", dir=ROOT / ".reprostamp"))
    print(f"Evidence directory: {output}", flush=True)
    cache = args.cache.resolve() if args.cache else output / "cache"
    invoke("prepare", "--cache", cache, message="Starter dependency cache ready")
    test_invalid(output, cache)
    mock = EXAMPLES / "field-notes.json"
    generated = output / "field-notes"
    command = ("generate", "--description", EXAMPLES / "field-notes.txt", "--response-file", mock,
               "--cache", cache, "--out", generated)
    preview = json.loads(invoke(*command))
    assert preview["provider"] == "deterministic" and not generated.exists()
    invoke(*command, "--approve", "0" * 64, expected=2, message="approval_mismatch")
    assert not generated.exists()
    print(invoke(*command, "--approve", preview["approval_sha256"], message="Starter validation passed"), end="", flush=True)
    first = check_export(generated, mock)
    metadata = json.loads((generated / "configuration-request.json").read_bytes())
    assert metadata["configuration_sha256"] == first["config_sha256"]
    assert metadata["usage"] == {"output_bytes": mock.stat().st_size, "input_tokens": None, "output_tokens": None}
    print("PASS checked-in mock, approval, invalid configuration, and offline receipt", flush=True)
    if args.mock_only:
        return

    studio = EXAMPLES / "studio-requests.json"
    second = output / "studio-requests"
    print(invoke("generate", "--config", studio, "--cache", cache, "--out", second, message="Starter validation passed"),
          end="", flush=True)
    other = check_export(second, studio)
    assert first["template"] == other["template"] and first["config_sha256"] != other["config_sha256"]
    extracted = output / "extracted"
    with zipfile.ZipFile(second / "source.zip") as archive:
        archive.extractall(extracted)
    rerun = output / "rerun"
    invoke("validate", "--source", extracted, "--cache", cache, "--out", rerun, message="Starter validation passed")
    copied = check_export(rerun, studio)
    assert copied["artifacts"]["source.zip"] == other["artifacts"]["source.zip"]
    assert copied["harness_sha256"] == first["harness_sha256"]
    bad = output / "tampered.zip"
    with zipfile.ZipFile(second / "receipt.zip") as archive, zipfile.ZipFile(bad, "x") as mutated:
        for member in archive.infolist():
            data = archive.read(member)
            mutated.writestr(member, (b"!" + data[1:]) if member.filename == "source.zip" else data)
    invoke("verify", bad, expected=2, message="Artifact SHA-256 mismatch for 'source.zip'")
    print(f"PASS second configuration, rerun from unzipped source, and tamper detection. Evidence in {output}")


if __name__ == "__main__":
    main()
