#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/checkout"
BASE_TAG = "checkout-base"
HEAD_TAG = "checkout-fixed"
AUTHOR_DATE = "2026-01-01T00:00:00Z"


def git(repo: Path, *args: str) -> str:
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env.update(
        GIT_AUTHOR_DATE=AUTHOR_DATE, GIT_COMMITTER_DATE=AUTHOR_DATE,
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1",
    )
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=BuildVerify Fixture", "-c",
         "user.email=fixture@buildverify.invalid", "-c", "core.hooksPath=/dev/null", *args],
        env=env, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()


def fixture_commits(destination: Path) -> tuple[str, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=destination.parent) as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(FIXTURE / "app", repo, ignore=shutil.ignore_patterns(
            "node_modules", "dist", ".git", ".DS_Store", ".env*",
        ))
        for path in repo.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        git(repo, "init", "--initial-branch=main", "--object-format=sha1", "--template=")
        git(repo, "add", "--all")
        git(repo, "commit", "-m", "Reproduce checkout discount bug")
        git(repo, "tag", BASE_TAG)
        git(repo, "apply", str(FIXTURE / "fix.patch"))
        git(repo, "commit", "-am", "Subtract the checkout discount")
        git(repo, "tag", HEAD_TAG)
        refs = tuple(git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}") for tag in (BASE_TAG, HEAD_TAG))

        if not destination.exists():
            try:
                repo.rename(destination)
            except OSError:
                if not destination.exists():
                    raise
        existing = tuple(
            git(destination, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
            for tag in (BASE_TAG, HEAD_TAG)
        )
        if existing != refs:
            raise ValueError(f"The existing fixture has different commits at {destination}.")
        return existing[0], existing[1]


def warm_cache(image: str, cache: Path, *packages: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for package in packages:
        with tempfile.TemporaryDirectory(prefix="buildverify-locks-") as temp:
            inputs = Path(temp).resolve()
            inputs.chmod(0o755)
            for name in ("package.json", "package-lock.json"):
                shutil.copyfile(package / name, inputs / name)
            subprocess.run(
                ["docker", "run", "--rm", "--init", "--pull=never", "--read-only", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                 "--tmpfs", "/tmp:rw,nosuid,nodev,exec,size=768m,mode=1777",
                 "--env", "HOME=/tmp", "--workdir", "/tmp",
                 "-v", f"{inputs}:/locks:ro", "-v", f"{cache}:/cache", image,
                 "sh", "-ec", "cp /locks/* /tmp/; npm ci --prefer-offline --ignore-scripts "
                 "--include=dev --no-audit --no-fund --cache /cache"],
                check=True, stdout=None, timeout=120,
            )


def main() -> None:
    profile_path = ROOT / "profiles/checkout.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    repo = (profile_path.parent / profile["repository"]).resolve()
    cache = (profile_path.parent / profile["npm_cache"]).resolve()
    harness = (profile_path.parent / profile["harness"]).resolve()
    base, head = fixture_commits(repo)
    warm_cache(profile["runner_image"], cache, FIXTURE / "app", harness)
    print(json.dumps({"repo": str(repo), "base": base, "head": head}))


if __name__ == "__main__":
    main()
