"""CLI for bounded task-tracker generation and validation."""

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from .app_context import RepoMap
from .app_source import APP_FILES, STACK, AppPatch, read_bounded, render_app, snapshot_app, write_json
from .app_workflow import ARMS, SINGLE, Workflow, run_workflow
from .integrity import hash_json
from .model_provider import SuggestionError
from .runner import DockerError, runner_platform
from .starter import AppValidation, validate_source
from .starter_runner import IMAGE, TEMPLATE, check_cache


def add_app_command(commands) -> None:
    parser = commands.add_parser("app", help="generate, validate, and benchmark bounded task trackers")
    actions = parser.add_subparsers(dest="action", required=True)
    generate = actions.add_parser("generate", help="generate and validate a task tracker")
    choose = generate.add_mutually_exclusive_group(required=True)
    choose.add_argument("--plan", type=Path, help="golden app patch JSON")
    choose.add_argument("--requirements", type=Path, help="description for the local model")
    generate.add_argument("--stack", choices=[STACK], default=STACK)
    generate.add_argument("--arm", choices=ARMS, default=SINGLE)
    generate.add_argument("--failure", type=Path, help="reviewed diagnostic text for context ranking")
    generate.add_argument("--approve", metavar="SHA256")
    validate = actions.add_parser("validate", help="revalidate the files in an extracted export")
    validate.add_argument("--source", type=Path, required=True)
    benchmark = actions.add_parser("benchmark", help="run both evaluation arms on each seeded fixture")
    benchmark.add_argument("--suite", type=Path, required=True)
    benchmark.add_argument("--approve", metavar="SHA256")
    for command in (generate, benchmark):
        command.add_argument("--ollama-model", help="installed model for the patch stage")
        command.add_argument("--planner-model", help="installed lower-cost model for planning and review")
        command.add_argument("--max-input-bytes", type=int, default=8192)
    for command in (generate, validate, benchmark):
        command.add_argument("--cache", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=app_command)


def validate_app(patch: AppPatch, source: Path, out: Path, cache: Path, platform: str, temporary: Path,
                 *, origin: str, expected: AppPatch | None = None, frozen_harness: Path | None = None) -> int:
    oracle = expected or patch
    app = AppValidation(APP_FILES, hash_json(asdict(patch)), hash_json(asdict(oracle)), origin, oracle.config,
                        oracle.presentation.expectations(), frozen_harness)
    return validate_source(source, patch.config, cache, platform, out, temporary, app=app)


def fresh_output(out: Path, cache: Path) -> None:
    if out.exists():
        raise ValueError("Choose a new --out directory for each app run.")
    if out.is_relative_to(cache) or cache.is_relative_to(out):
        raise ValueError("Use separate output and dependency cache directories.")


def acceptance_platform(cache: Path) -> str:
    platform = runner_platform(IMAGE)
    check_cache(cache, platform)
    return platform


def show_or_approve(preview: dict, approval: str | None) -> str | None:
    digest = hash_json(preview)
    if approval is None:
        print(json.dumps({**preview, "approval_sha256": digest}, indent=2, ensure_ascii=False))
        return None
    if approval != digest:
        raise SuggestionError("approval_mismatch", "Review the current preview and approve its exact SHA-256.")
    return digest


def read_description(path: Path) -> str:
    text = read_bounded(path, 4096).decode("utf-8").strip()
    if not text or "\0" in text:
        raise ValueError("Provide nonempty UTF-8 requirements or diagnostics.")
    return text


def run_app(args: argparse.Namespace) -> int:
    cache, out = args.cache.resolve(), args.out.resolve()
    fresh_output(out, cache)
    if args.action == "benchmark":
        from .app_benchmark import benchmark
        return benchmark(args, cache, out)

    source = args.source.resolve() if args.action == "validate" else None
    if source is not None and (out.is_relative_to(source) or cache.is_relative_to(source)):
        raise ValueError("Keep the output and dependency cache outside the extracted app.")
    patch = workflow = evidence = None
    origin = "revalidation"
    if args.action == "generate":
        if args.plan:
            if any((args.ollama_model is not None, args.planner_model is not None, args.failure,
                    args.approve, args.arm != SINGLE, args.max_input_bytes != 8192)):
                raise ValueError("Use model, diagnostic, arm, and approval options with --requirements.")
            patch = AppPatch.decode(read_bounded(args.plan, 8192))
            origin = "golden"
        else:
            if not args.ollama_model:
                raise ValueError("Choose --ollama-model when using --requirements.")
            index = RepoMap()
            index.refresh(TEMPLATE)
            workflow = Workflow(args.arm, read_description(args.requirements),
                                read_description(args.failure) if args.failure else "", index, args.max_input_bytes,
                                args.ollama_model, args.planner_model)
            digest = show_or_approve(
                {"experimental": True, "output_directory": str(out), "cache_directory": str(cache),
                 "runner_image": IMAGE, "workflow": workflow.preview()}, args.approve,
            )
            if digest is None:
                return 0
            evidence = {"origin": "experimental", "approval_sha256": digest, "status": "started"}
            origin = "experimental"

    with tempfile.TemporaryDirectory(prefix="reprostamp-app-") as directory:
        temporary = Path(directory).resolve()
        snapshot = temporary / "source"
        if source is not None:
            patch = snapshot_app(source, snapshot)
        platform = acceptance_platform(cache)
        out.mkdir(mode=0o700, parents=True)
        if workflow is not None:
            try:
                patch = run_workflow(workflow, evidence)
                evidence["status"] = "patch_accepted"
            except ValueError as error:
                evidence.update(status="rejected", reason=str(error))
                raise
            finally:
                write_json(out / "generation.json", evidence)
        if source is None:
            render_app(snapshot, patch)
        return validate_app(patch, snapshot, out, cache, platform, temporary, origin=origin)


def app_command(args: argparse.Namespace) -> int:
    try:
        return run_app(args)
    except SuggestionError as error:
        print(f"reprostamp app [{error.reason}]: {error}", file=sys.stderr)
    except (OSError, ValueError, DockerError, subprocess.SubprocessError) as error:
        print(f"reprostamp app: {error}", file=sys.stderr)
    return 2
