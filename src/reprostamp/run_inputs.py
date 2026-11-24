import hashlib
from dataclasses import asdict
from pathlib import Path

from .integrity import hash_file, hash_json
from .profile import Profile
from .repository import Entry, Repository
from .runner import RUNNER_CONTRACT


def run_plan(profile: Profile) -> dict:
    plan = {
        "engines": list(profile.engines),
        "case_ids": [profile.expected_failure.case_id, *profile.required_regressions],
    }
    if profile.review:
        plan["review"] = {"engine": profile.review.engine, "routes": [asdict(item) for item in profile.review.routes]}
    return plan


def fingerprint_inputs(
    repo: Repository, profile: Profile, harness: Path, base_sha: str,
    base: dict[str, Entry], head: dict[str, Entry], changes: list[str], platform: str | None,
) -> dict:
    oracle = {
        "expected_failure": asdict(profile.expected_failure),
        "required_regressions": profile.required_regressions,
    }
    harness_files = {}
    for path in harness.rglob("*"):
        if path.is_file():
            with path.open("rb") as file:
                harness_files[path.relative_to(harness).as_posix()] = hash_file(file)

    settings = {**asdict(profile.browser), "timeout_seconds": profile.timeout_seconds, "attempts_per_side": 2}
    effective_profile = {
        **oracle, **run_plan(profile), "runner_image": profile.runner_image,
        "editable_paths": profile.editable_paths, "settings": settings,
    }
    oracle_sha256 = hash_json({**oracle, "harness": harness_files})
    if profile.review:
        effective_profile["oracle_sha256"] = oracle_sha256
    return {
        "repository_sha256": hash_json(sorted(repo.git("rev-list", "--max-parents=0", base_sha).decode().split())),
        "diff_sha256": hash_json([
            {"path": path, "base": asdict(base[path]) if path in base else None,
             "head": asdict(head[path]) if path in head else None}
            for path in changes
        ]),
        "lockfile_sha256": {
            side: hashlib.sha256(repo.git("cat-file", "blob", tree["package-lock.json"].blob)).hexdigest()
            for side, tree in (("base", base), ("head", head))
        },
        "oracle_sha256": oracle_sha256,
        "profile_sha256": hash_json(effective_profile),
        "runner_image": profile.runner_image,
        "runner_platform": platform,
        "runner_contract": RUNNER_CONTRACT,
        "settings": settings,
    }
