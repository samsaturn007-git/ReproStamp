"""Run a paired app-generation evaluation with an independent executable oracle."""

import random
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .app import acceptance_platform, read_description, show_or_approve, validate_app
from .app_context import RepoMap
from .app_source import EDITABLE_FILES, SEARCH_TERMS, TASKS, AppPatch, decode_object, read_bounded, render_app, write_json
from .app_workflow import ARMS, PLAN_REVIEW, Workflow, run_workflow
from .integrity import canonical_json, hash_json
from .model_provider import ModelOutput
from .runner import DockerError, freeze_harness
from .starter_runner import APP_CASE_IDS, HARNESS, IMAGE, SETTINGS, TEMPLATE, input_hash

FIXTURE_ID = re.compile(r"[a-z][a-z0-9-]{0,39}")
ORACLE = "Independent Playwright health, task CRUD, task lifecycle, and requested presentation in three engines"


@dataclass(frozen=True)
class Fixture:
    id: str
    requirements: str
    expected: AppPatch
    mock_draft: AppPatch
    search_terms: tuple[str, ...]
    target_paths: tuple[str, ...]


def load_suite(path: Path) -> tuple[int, list[Fixture], str]:
    data = decode_object(read_bounded(path, 65_536))
    if data.keys() != {"seed", "fixtures"} or type(data["seed"]) is not int:
        raise ValueError("An evaluation suite needs an integer seed and fixtures.")
    rows = data["fixtures"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
        raise ValueError("An evaluation suite needs one to twelve fixtures.")
    fixtures = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.keys() != {"id", "requirements", "expected", "mock_draft", "search_terms", "target_paths"}:
            raise ValueError("Invalid evaluation fixture fields.")
        name = row["id"]
        if not isinstance(name, str) or not FIXTURE_ID.fullmatch(name) or name in seen:
            raise ValueError("Evaluation fixture IDs must be unique lowercase slugs.")
        seen.add(name)
        filename = row["requirements"]
        if not isinstance(filename, str) or filename != f"{name}.txt":
            raise ValueError("The requirements file must be named for the fixture and sit beside the suite.")
        search, paths = row["search_terms"], row["target_paths"]
        if not isinstance(search, list) or len(search) > 5 or any(term not in SEARCH_TERMS for term in search):
            raise ValueError("Evaluation search terms must be selected from the supported symbols.")
        if (not isinstance(paths, list) or not paths or any(path not in EDITABLE_FILES for path in paths)
                or len(set(paths)) != len(paths)):
            raise ValueError("Evaluation target paths must be supported template source paths.")
        fixtures.append(Fixture(name, read_description(path.parent / filename),
                                AppPatch.decode(canonical_json(row["expected"])),
                                AppPatch.decode(canonical_json(row["mock_draft"])), tuple(search), tuple(paths)))
    return data["seed"], fixtures, hash_json([asdict(fixture) for fixture in fixtures])


def mock_response(fixture: Fixture, stage: str) -> ModelOutput:
    if stage == "plan":
        return ModelOutput(canonical_json({"tasks": TASKS, "search_terms": fixture.search_terms}))
    patch = fixture.mock_draft if stage == "generate" else fixture.expected
    return ModelOutput(canonical_json(asdict(patch)))


def run_trial(fixture: Fixture, workflow: Workflow, directory: Path, cache: Path, platform: str, harness: Path) -> dict:
    directory.mkdir(mode=0o700, parents=True)
    live = workflow.model is not None
    row = {"fixture": fixture.id, "arm": workflow.arm, "origin": "experimental" if live else "golden",
           "attempts": 1, "billed_model_usd": 0, "result": "incomplete", "failure_mode": None}
    started = time.monotonic()
    try:
        mock = None if live else lambda stage: mock_response(fixture, stage)
        patch = run_workflow(workflow, row, mock)
        context = row["context_metrics"]
        context["target_paths"] = fixture.target_paths
        context["target_paths_selected"] = len(set(context["selected_paths"]) & set(fixture.target_paths))
        with tempfile.TemporaryDirectory(prefix="reprostamp-eval-") as directory_name:
            temporary = Path(directory_name).resolve()
            source = temporary / "source"
            render_app(source, patch)
            exit_code = validate_app(patch, source, directory, cache, platform, temporary,
                                     origin=row["origin"], expected=fixture.expected, frozen_harness=harness)
        receipt = decode_object((directory / "receipt.json").read_bytes())
        payload = receipt["payload"]
        row["receipt_sha256"] = receipt["payload_sha256"]
        row["checks"] = [
            {"engine": run["engine"], "execution_state": run["execution_state"],
             "reason": run["reason"], "checks": {case["case_id"]: case["status"] for case in run["checks"]}}
            for run in payload["runs"]
        ]
        row["result"] = payload["result"]
        if exit_code:
            row["failure_mode"] = "assertion_failure" if exit_code == 1 else "runner_incomplete"
    except (ValueError, OSError, DockerError) as error:
        stages = row.get("calls", [])
        row["result"] = "rejected" if isinstance(error, ValueError) else "incomplete"
        row["failure_mode"] = (stages[-1]["status"] if stages and stages[-1]["status"] != "received"
                               else type(error).__name__)
        row["detail"] = str(error)
    finally:
        row["wall_ms"] = round((time.monotonic() - started) * 1000)
        write_json(directory / "trial.json", row)
    return row


def totals(rows: list[dict]) -> dict:
    calls = [call for row in rows for call in row.get("calls", []) if call["invoked"]]
    summary = {
        "n": len(rows), "passed": sum(row["result"] == "passed" for row in rows),
        "attempts": sum(row["attempts"] for row in rows),
        "wall_ms": sum(row["wall_ms"] for row in rows), "model_calls": len(calls),
        "request_bytes": sum(call.get("input_bytes", 0) for call in calls),
        "billed_model_usd": sum(row["billed_model_usd"] for row in rows),
    }
    for metric in ("input_tokens", "output_tokens"):
        values = [(call.get("usage") or {}).get(metric) for call in calls]
        present = [value for value in values if value is not None]
        summary[metric] = sum(present) if present else None
        summary[f"{metric}_reported_calls"] = len(present)
    return summary


def report_lines(report: dict) -> list[str]:
    lines = ["# App generation benchmark", "", f"Mode **{report['mode']}**. Paired sample **N = {report['n']}** per arm.",
             "", report["oracle"] + ".", "",
             "| Arm | Passed / N | Attempts | Calls | Request bytes | Input tokens | Output tokens | API USD | Wall seconds |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for arm, value in report["summary"].items():
        def tokens(key: str) -> str:
            count = value[key]
            return "Unavailable" if count is None else f"{count} ({value[key + '_reported_calls']}/{value['model_calls']} calls)"
        lines.append(f"| {arm} | {value['passed']} / {value['n']} | {value['attempts']} | {value['model_calls']} "
                     f"| {value['request_bytes']} | {tokens('input_tokens')} | {tokens('output_tokens')} "
                     f"| {value['billed_model_usd']} | {value['wall_ms'] / 1000:.2f} |")
    lines += ["", "| Fixture | Arm | Result | Failure mode | Selected / full context bytes | Target files found | Evidence |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["trials"]:
        metrics = row.get("context_metrics") or {}
        size = (f"{metrics['selected_context_bytes']} / {metrics['full_context_bytes']}" if metrics else "Unavailable")
        hits = (f"{metrics['target_paths_selected']} / {len(metrics['target_paths'])}"
                if "target_paths_selected" in metrics else "Unavailable")
        prefix = f"{row['fixture']}/{row['arm']}"
        evidence = f"[Trial]({prefix}/trial.json)"
        if row.get("receipt_sha256"):
            evidence += f" · [Receipt]({prefix}/receipt.zip)"
        lines.append(f"| {row['fixture']} | {row['arm']} | {row['result']} | {row['failure_mode'] or 'None'} "
                     f"| {size} | {hits} | {evidence} |")
    lines += ["", report["limitations"], "", "[Raw report and run manifest](report.json)", ""]
    return lines


def benchmark(args, cache: Path, out: Path) -> int:
    seed, fixtures, suite_sha = load_suite(args.suite.resolve())
    live = args.ollama_model is not None
    if not live and (args.approve is not None or args.planner_model is not None):
        raise ValueError("Approval and planner model require --ollama-model.")
    index = RepoMap()
    rebuilt = index.refresh(TEMPLATE)
    factory = {}
    for fixture in fixtures:
        for arm in ARMS:
            factory[fixture.id, arm] = Workflow(arm, fixture.requirements, "", index, args.max_input_bytes,
                                                 args.ollama_model, args.planner_model)
    preview = {"mode": "experimental" if live else "scripted golden", "suite_sha256": suite_sha,
               "seed": seed, "runner_image": IMAGE, "browser_settings": SETTINGS,
               "cache_directory": str(cache), "output_directory": str(out)}
    if live:
        preview["workflows"] = [{"fixture": name, **workflow.preview()}
                                for (name, _), workflow in factory.items()]
        approval = show_or_approve(preview, args.approve)
        if approval is None:
            return 0
        preview["approval_sha256"] = approval
    platform = acceptance_platform(cache)
    out.mkdir(mode=0o700, parents=True)
    results = []
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="reprostamp-eval-oracle-") as oracle_directory:
        harness = Path(oracle_directory).resolve() / "harness"
        freeze_harness(HARNESS, harness)
        harness_hash = input_hash(harness, tuple(path.name for path in harness.iterdir()))
        for fixture in fixtures:
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                print(f"Evaluating {fixture.id} · {arm}", flush=True)
                results.append(run_trial(fixture, factory[fixture.id, arm], out / fixture.id / arm, cache, platform, harness))
    limitations = (
        "Scripted outputs include a seeded bad draft and a corrected review. The measured differences exercise "
        "the workflow and oracle. They do not estimate model quality or stochastic variance. "
        if not live else
        "One local model sample per fixture and arm. An outcome may vary with the model, prompt, or runtime. "
        "The arms differ in stages, per-stage output limits, and model choice when a planner model is supplied. "
    )
    limitations += (
        "Both arms share the same attempt count, browser environment, 512 aggregate output token budget, and "
        "independent acceptance suite. Context byte counts compare the selected excerpts with the entire eligible "
        "source set. No full-context generation was run. Local compute, energy, and hardware costs are unmeasured."
    )
    report = {**preview, "n": len(fixtures), "runner_platform": platform, "checks": APP_CASE_IDS, "oracle": ORACLE,
              "harness_sha256": harness_hash,
              "index": {"files_parsed": rebuilt, "files_reparsed_without_changes": index.refresh(TEMPLATE)},
              "trials": results, "summary": {arm: totals([row for row in results if row["arm"] == arm]) for arm in ARMS},
              "limitations": limitations}
    write_json(out / "report.json", report)
    (out / "report.md").write_text("\n".join(report_lines(report)), encoding="utf-8")
    print(f"Benchmark report saved in {out / 'report.md'}.")
    return 0
