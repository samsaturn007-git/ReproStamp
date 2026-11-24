import argparse
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path

from .integrity import canonical_json, hash_json
from .model_provider import (Budget, DeterministicProvider, OllamaProvider, OpenAIProvider, ProviderError,
                             SuggestionError, output_usage, review_request)
from .receipt import export_bundle, verify_bundle
from .receipt_schema import SHA256, enum, integer, record, string, validate_artifact_paths
from .repair import save_metadata
from .runner import ARTIFACT_NAMES, DockerError, freeze_harness, runner_platform
from .starter_config import CONFIG_LIMIT, FORMAT, StarterConfig
from .starter_runner import CASE_IDS, DEPENDENCIES, ENGINES, HARNESS, IMAGE, SETTINGS, TEMPLATE, check_cache, input_hash, prepare_cache, run_engine


TEMPLATE_ID = "task-tracker/v1"
SOURCE_FILES = (*DEPENDENCIES, ".gitignore", "README.md", "index.html", "main.py", "tsconfig.json",
                "src/main.tsx", "src/style.css", "starter.json")


def add_starter_command(commands) -> None:
    starter = commands.add_parser("starter", help="generate and validate a task-tracker starter")
    actions = starter.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare", help="provision locked dependencies for offline validation")
    generate = actions.add_parser("generate", help="export the configured source and validate it")
    validate = actions.add_parser("validate", help="validate an extracted starter with the independent harness")
    for action in (prepare, generate, validate):
        action.add_argument("--cache", type=Path, required=True, help="owner-managed runner dependency cache directory")
    for action in (generate, validate):
        action.add_argument("--out", type=Path, required=True, help="new output directory")
    config = generate.add_mutually_exclusive_group(required=True)
    config.add_argument("--config", type=Path, help="local typed configuration JSON")
    config.add_argument("--description", type=Path, help="plain-text task tracker description to preview and approve")
    provider = generate.add_mutually_exclusive_group()
    provider.add_argument("--response-file", type=Path, help="deterministic model response JSON")
    provider.add_argument("--ollama-model", help="installed model on the local Ollama server")
    provider.add_argument("--openai-model", help="opt in to the OpenAI Responses API with this model")
    generate.add_argument("--approve", metavar="SHA256", help="approval digest from the reviewed model request")
    generate.add_argument("--max-input-bytes", type=int, default=4096)
    generate.add_argument("--max-output-bytes", type=int, default=CONFIG_LIMIT)
    generate.add_argument("--max-output-tokens", type=int, default=512)
    validate.add_argument("--source", type=Path, required=True, help="extracted starter source directory")
    verify = actions.add_parser("verify", help="check a starter validation receipt bundle offline")
    verify.add_argument("bundle", type=Path)
    starter.set_defaults(handler=starter_command)


def read_config(path: Path) -> StarterConfig:
    with path.open("rb") as file:
        return StarterConfig.decode(file.read(CONFIG_LIMIT + 1))


def model_request(args, out: Path):
    if args.response_file:
        provider = DeterministicProvider(args.response_file.resolve())
    elif args.ollama_model is not None:
        provider = OllamaProvider(args.ollama_model, FORMAT)
    elif args.openai_model and args.openai_model.strip() == args.openai_model:
        provider = OpenAIProvider(args.openai_model, FORMAT)
    else:
        raise ValueError("Choose a model provider when using --description.")
    budget = Budget(args.max_input_bytes, args.max_output_bytes, args.max_output_tokens)
    with args.description.open("rb") as file:
        description = file.read(budget.input_bytes + 1)
    if len(description) > budget.input_bytes:
        raise SuggestionError("input_budget_exceeded", "The description exceeded the configured input byte budget.")
    text = description.decode("utf-8").strip()
    if not text or "\0" in text:
        raise ValueError("Provide a nonempty UTF-8 task tracker description.")
    context = {"description": text}
    encoded, request, digest = review_request(context, FORMAT.instructions, budget, {
        "schema_version": 1, "provider": provider.identifier, "template": TEMPLATE_ID, "output_directory": str(out),
    })
    if args.approve is None:
        preview = {**request, "context": context, "instructions": FORMAT.instructions, "approval_sha256": digest}
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return None
    if args.approve != digest:
        raise SuggestionError("approval_mismatch", "Review the current preview and approve its exact SHA-256.")
    return provider, budget, encoded, {**request, "approval_sha256": digest}


def request_config(out: Path, provider, budget, context: str, request: dict) -> StarterConfig:
    metadata = {**request, "status": "request_started", "usage": None}
    save_metadata(out, metadata, filename="configuration-request.json")
    response = None
    try:
        response = provider.propose(context, budget)
        if len(response.content) > budget.output_bytes:
            raise SuggestionError("output_budget_exceeded", "The provider exceeded the configured output byte budget.")
        try:
            config = StarterConfig.decode(response.content)
        except ValueError as error:
            raise SuggestionError("malformed_output", str(error)) from error
        metadata.update(status="accepted", configuration_sha256=hash_json(asdict(config)))
        return config
    except SuggestionError as error:
        if isinstance(error, ProviderError):
            response = error.output
        metadata.update(status="rejected", reason=error.reason)
        raise
    finally:
        if response is not None:
            metadata["usage"] = output_usage(response)
        save_metadata(out, metadata, filename="configuration-request.json")


def render_source(destination: Path, config: StarterConfig) -> None:
    (destination / "src").mkdir(parents=True)
    for filename in SOURCE_FILES:
        path = destination / filename
        if filename == "starter.json":
            path.write_bytes(canonical_json(asdict(config)) + b"\n")
        else:
            shutil.copyfile(TEMPLATE / filename, path)


def snapshot_source(source: Path, destination: Path) -> StarterConfig:
    if not stat.S_ISDIR((source / "src").lstat().st_mode):
        raise ValueError("The starter src directory must be a regular directory.")
    (destination / "src").mkdir(parents=True)
    for filename in SOURCE_FILES:
        path = source / filename
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError(f"Starter source file {filename!r} must be a regular file.")
        with path.open("rb") as file:
            data = file.read(1_048_577)
        if len(data) > 1_048_576:
            raise ValueError(f"Starter source file {filename!r} exceeds 1 MiB.")
        if filename in DEPENDENCIES and data != (TEMPLATE / filename).read_bytes():
            raise ValueError(f"Starter dependency input {filename!r} must match the maintained template lock.")
        (destination / filename).write_bytes(data)
    return read_config(destination / "starter.json")


def validation_result(runs: list[dict]) -> str:
    if any(run["execution_state"] == "incomplete" for run in runs):
        return "incomplete"
    return "failed" if any(check["status"] == "assertion_failed" for run in runs for check in run["checks"]) else "passed"


def validate_receipt(payload: dict) -> None:
    record(payload, "kind template config_sha256 runner_image runner_platform harness_sha256 browser_settings checks "
           "result runs artifacts", "starter validation payload")
    enum(payload["kind"], ("starter_validation",), "receipt kind")
    enum(payload["template"], (TEMPLATE_ID,), "template")
    for key in ("config_sha256", "harness_sha256"):
        string(payload[key], key, SHA256)
    string(payload["runner_image"], "runner image")
    string(payload["runner_platform"], "runner platform")
    if payload["browser_settings"] != SETTINGS or payload["checks"] != list(CASE_IDS):
        raise ValueError("Unexpected starter validation plan.")
    runs = payload["runs"]
    if not isinstance(runs, list) or len(runs) != len(ENGINES):
        raise ValueError("The starter receipt requires one run per supported engine.")
    paths = {"receipt.md", "source.zip"}
    for engine, run in zip(ENGINES, runs, strict=True):
        record(run, "engine execution_state reason detail duration_ms browser_build checks logs", "starter run")
        enum(run["engine"], (engine,), "browser engine")
        enum(run["execution_state"], ("completed", "incomplete"), "execution state")
        integer(run["duration_ms"], 0, 2**53 - 1, "run duration")
        completed = run["execution_state"] == "completed"
        if completed and (run["reason"] is not None or run["detail"] is not None):
            raise ValueError("A completed starter run cannot have an execution error.")
        if not completed:
            string(run["reason"], "execution reason")
            string(run["detail"], "execution detail")
        build = run["browser_build"]
        if build is not None or completed:
            record(build, "version platform", "browser build")
            string(build["version"], "browser version")
            string(build["platform"], "browser platform")
        paths.update(validate_artifact_paths(run["logs"], {role: f"{engine}/{role}.log" for role in ("app", "harness")}, "log"))
        if not isinstance(run["checks"], list):
            raise ValueError("A starter run must list its observed checks.")
        seen = set()
        for check in run["checks"]:
            record(check, "case_id status playwright_status duration_ms assertion artifacts detail application_location", "starter check")
            case_id = check["case_id"]
            enum(case_id, CASE_IDS, "starter check ID")
            if case_id in seen:
                raise ValueError("Duplicate starter check.")
            seen.add(case_id)
            allowed = ("passed", "assertion_failed") if completed else ("passed", "assertion_failed", "missing", "error", "unsupported")
            enum(check["status"], allowed, "starter check outcome")
            integer(check["duration_ms"], 0, 2**53 - 1, "check duration")
            paths.update(validate_artifact_paths(check["artifacts"],
                         {kind: f"{engine}/{case_id}/{name}" for kind, name in ARTIFACT_NAMES.items()}, "starter check"))
        if completed and seen != set(CASE_IDS):
            raise ValueError("A completed starter run must record all expected checks.")
    enum(payload["result"], (validation_result(runs),), "validation result")
    manifest = payload["artifacts"]
    if not isinstance(manifest, dict) or manifest.keys() != paths:
        raise ValueError("The starter manifest does not match the source and check evidence.")
    for path, file in manifest.items():
        record(file, "sha256 size", f"manifest entry {path}")
        string(file["sha256"], "artifact digest", SHA256)
        integer(file["size"], 0, 2**53 - 1, "artifact size")


def validate_source(source: Path, config: StarterConfig, cache: Path, platform: str, out: Path, temporary: Path) -> int:
    harness = temporary / "harness"
    freeze_harness(HARNESS, harness)
    harness_hash = input_hash(harness, tuple(path.name for path in harness.iterdir()))
    with zipfile.ZipFile(out / "source.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in sorted(SOURCE_FILES):
            member = zipfile.ZipInfo(filename)
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(member, (source / filename).read_bytes())
    run_id = f"starter-{uuid.uuid4().hex}"
    runs = []
    artifacts = {"receipt.md", "source.zip"}
    lines = ["# ReproStamp starter validation", "", "[Download source](source.zip)", "",
             "| Browser | Build | Execution | Health | Task CRUD | Browser journey |",
             "| --- | --- | --- | --- | --- | --- |"]
    for engine in ENGINES:
        run = run_engine(engine, run_id, source, config, cache, harness, temporary, out)
        runs.append(run)
        checks = {check["case_id"]: check["status"] for check in run["checks"]}
        version = (run["browser_build"] or {}).get("version", "Unavailable")
        states = [checks.get(case, "missing") for case in CASE_IDS]
        lines.append("| " + " | ".join([engine, version, run["execution_state"], *states]) + " |")
        print(f"{engine} {version} · {run['execution_state']} · {', '.join(states)}", flush=True)
        artifacts.update(run["logs"].values())
        for check in run["checks"]:
            artifacts.update(check["artifacts"].values())
    result = validation_result(runs)
    lines += ["", f"Validation **{result}**.", "", "See [receipt.json](receipt.json) for check evidence and hashes.", ""]
    (out / "receipt.md").write_text("\n".join(lines), encoding="utf-8")
    export_bundle(out, {"kind": "starter_validation", "template": TEMPLATE_ID, "config_sha256": hash_json(asdict(config)),
                        "runner_image": IMAGE, "runner_platform": platform, "harness_sha256": harness_hash,
                        "browser_settings": SETTINGS, "checks": list(CASE_IDS), "result": result, "runs": runs},
                  artifacts, validate_receipt)
    print(f"Starter validation {result}. Source and receipt saved in {out}.")
    return {"passed": 0, "failed": 1, "incomplete": 3}[result]


def run_starter(args: argparse.Namespace) -> int:
    if args.action == "verify":
        receipt = verify_bundle(args.bundle, validate=validate_receipt)
        print(f"Integrity verified: {receipt['payload_sha256']} ({len(receipt['payload']['artifacts'])} files)")
        print(f"Recorded starter validation: {receipt['payload']['result']}")
        return 0
    cache = args.cache.resolve()
    if args.action == "prepare":
        prepare_cache(cache)
        print(f"Starter dependency cache ready at {cache}.")
        return 0
    out = args.out.resolve()
    if out.exists():
        raise ValueError("Choose a new --out directory for each starter run.")
    if out.is_relative_to(cache) or cache.is_relative_to(out):
        raise ValueError("Use separate output and dependency cache directories.")
    source = args.source.resolve() if args.action == "validate" else None
    if source is not None and (out.is_relative_to(source) or cache.is_relative_to(source)):
        raise ValueError("Keep the output and dependency cache outside the starter source directory.")
    request = config = None
    if args.action == "generate":
        if args.config is not None:
            if any(value is not None for value in (args.response_file, args.ollama_model, args.openai_model, args.approve)):
                raise ValueError("Choose either --config or --description with a model provider and approval.")
            config = read_config(args.config)
        else:
            request = model_request(args, out)
            if request is None:
                return 0
    with tempfile.TemporaryDirectory(prefix="reprostamp-starter-") as directory:
        temporary = Path(directory).resolve()
        snapshot = temporary / "source"
        if source is not None:
            config = snapshot_source(source, snapshot)
        platform = runner_platform(IMAGE)
        check_cache(cache, platform)
        out.mkdir(mode=0o700, parents=True)
        if request is not None:
            config = request_config(out, *request)
        if source is None:
            render_source(snapshot, config)
        return validate_source(snapshot, config, cache, platform, out, temporary)


def starter_command(args: argparse.Namespace) -> int:
    try:
        return run_starter(args)
    except SuggestionError as error:
        print(f"reprostamp starter [{error.reason}]: {error}", file=sys.stderr)
    except (OSError, ValueError, DockerError, subprocess.SubprocessError) as error:
        print(f"reprostamp starter: {error}", file=sys.stderr)
    return 2
