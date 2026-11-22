import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from ..profile import PolicyError, load_profile
from ..repository import Repository
from ..run_inputs import run_plan
from ..runner import freeze_harness
from .settings import ProfileRegistration, Registration


def freeze_inputs(repository: Registration, profile_registration: ProfileRegistration,
                  base_ref: str, head_ref: str, target: Path) -> tuple[str, str, dict]:
    repo = Repository(repository.path)
    profile = load_profile(profile_registration.path, repo.path)
    if any(target.is_relative_to(path) or path.is_relative_to(target)
           for path in (repo.path, profile.harness, profile.npm_cache)):
        raise PolicyError("invalid_storage", "Run storage must be separate from the registered inputs.")

    base, head = repo.resolve(base_ref), repo.resolve(head_ref)
    target.mkdir(mode=0o700, parents=True)
    try:
        frozen = target / "repository"
        object_format = "sha1" if len(base) == 40 else "sha256"
        subprocess.run(["git", "init", "--quiet", f"--object-format={object_format}", str(frozen)],
                       env=repo.env, capture_output=True, timeout=30, check=True)
        Repository(frozen).git(
            "-c", "protocol.file.allow=always", "fetch", "--no-tags", "--no-recurse-submodules",
            "--no-auto-maintenance", "--no-write-fetch-head", str(repo.path),
            f"{base}:refs/reprostamp/base", f"{head}:refs/reprostamp/head",
        )
        harness = target / "harness"
        freeze_harness(profile.harness, harness)
        snapshot = {
            **asdict(profile), "repository": str(frozen), "harness": str(harness),
            "npm_cache": str(profile.npm_cache),
        }
        (target / "profile.json").write_text(json.dumps(snapshot), encoding="utf-8")
    except BaseException:
        shutil.rmtree(target)
        raise
    return base, head, run_plan(profile)
