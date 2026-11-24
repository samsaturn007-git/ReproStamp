import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from uuid import UUID, uuid5

from ..cli import ReplayError, match_replay
from ..integrity import hash_file
from ..profile import load_profile
from ..repository import Repository, changed_paths
from ..run_inputs import fingerprint_inputs, run_plan
from ..runner import DockerError, run_attempt, runner_platform
from .failures import REPLAY_ATTEMPTS, replay_summary


def execution_id(run_id: UUID, fence: int) -> str:
    return uuid5(run_id, str(fence)).hex


def copy_snapshot(source: Path, target: Path) -> None:
    target.mkdir(mode=0o700, parents=True)
    for name in ("repository", "harness"):
        shutil.copytree(source / name, target / name)
    profile = json.loads((source / "profile.json").read_text(encoding="utf-8"))
    profile.update(repository=str(target / "repository"), harness=str(target / "harness"))
    (target / "profile.json").write_text(json.dumps(profile), encoding="utf-8")


def run_case_replay(row: dict, inputs: Path, folder: Path, record) -> None:
    selection = row["replay"]
    repo = Repository(inputs / "repository")
    profile = load_profile(inputs / "profile.json", repo.path)
    base, head = (repo.resolve(row[f"{side}_sha"]) for side in ("base", "head"))
    base_tree, head_tree = repo.tree(base), repo.tree(head)
    changes = changed_paths(base_tree, head_tree, profile)
    try:
        platform = runner_platform(profile.runner_image)
    except (DockerError, subprocess.TimeoutExpired) as error:
        raise ReplayError("replay_image_unavailable", f"The pinned runner image is unavailable. {error}") from error
    match_replay(
        selection["original"], {
            "base_sha": base, "head_sha": head, "plan": run_plan(profile),
            "inputs": fingerprint_inputs(repo, profile, profile.harness, base, base_tree, head_tree, changes, platform),
        }, None,
    )
    run_id = execution_id(row["id"], row["fence"])
    engine, side, case_id = (selection[key] for key in ("engine", "side", "case_id"))
    entries, commit = (base_tree, base) if side == "base" else (head_tree, head)
    build = selection["browser_build"]
    for number in range(1, REPLAY_ATTEMPTS + 1):
        record(engine, side, number)
        with tempfile.TemporaryDirectory(prefix=f"reprostamp-{run_id}-", dir=folder) as temp:
            workspace = Path(temp).resolve()
            app = workspace / "app"
            repo.export(entries, app)
            attempt = run_attempt(
                profile, run_id=run_id, side=side, number=number, commit=commit, engine=engine,
                app=app, harness=profile.harness, work_root=workspace, out_root=folder / "evidence", case_id=case_id,
            )
        if attempt.status == "completed":
            observed = asdict(attempt.browser_build)
            if (build is not None and observed != build) or observed["platform"] != platform:
                attempt = replace(attempt, status="incomplete", reason="replay_browser_build_changed",
                                  detail=f"The observed {engine} build differs from the controlled replay build.")
            else:
                build = observed
        record(engine, side, number, asdict(attempt))


def replay_output(folder: Path, row: dict, attempts: list[dict]) -> tuple[dict, list[dict]]:
    problem = folder / "replay-error.json"
    if problem.is_file():
        return json.loads(problem.read_text(encoding="utf-8")), []
    summary = replay_summary(attempts, row["fence"])
    if summary["sample_size"] != REPLAY_ATTEMPTS:
        raise ValueError("Case replay did not record five attempts.")
    artifacts = []
    output = folder / "evidence"
    for attempt in attempts:
        result = attempt["result"]
        if attempt["fence"] != row["fence"] or result is None:
            continue
        paths = {path: "log" for path in result["logs"].values()}
        for case in result["cases"]:
            paths.update({path: kind for kind, path in case["artifacts"].items()})
        for relative, kind in paths.items():
            path = (output / relative).resolve()
            if not path.is_relative_to(output) or not path.is_file():
                raise ValueError("A replay artifact is unavailable.")
            with path.open("rb") as file:
                artifacts.append({"kind": kind, "path": relative, "size": path.stat().st_size, "sha256": hash_file(file)})
    incomplete = bool(summary["infrastructure_failure"])
    return {
        "state": "incomplete" if incomplete else "completed",
        "reason": "case_replay_incomplete" if incomplete else "case_replay_finished",
        "detail": f"Recorded {REPLAY_ATTEMPTS} attempts for the selected browser and case.",
    }, artifacts
