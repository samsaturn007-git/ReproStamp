#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHOR_DATE = "2026-01-01T00:00:00Z"
COMMIT_MESSAGES = {
    "checkout": ("Reproduce checkout discount bug", "Subtract the checkout discount"),
    "shipping": ("Reproduce free-shipping threshold bug", "Include orders at the free-shipping threshold"),
}


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


def fixture_commits(destination: Path, fixture: str) -> tuple[str, str]:
    source = ROOT / "fixtures" / fixture
    base_tag, head_tag = f"{fixture}-base", f"{fixture}-fixed"
    base_message, head_message = COMMIT_MESSAGES[fixture]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=destination.parent) as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(source / "app", repo, ignore=shutil.ignore_patterns(
            "node_modules", "dist", ".git", ".DS_Store", ".env*",
        ))
        if fixture == "shipping":
            scaffold = ROOT / "fixtures/checkout/app"
            for name in ("package.json", "package-lock.json", "tsconfig.json"):
                shutil.copyfile(scaffold / name, repo / name)
        for path in repo.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        git(repo, "init", "--initial-branch=main", "--object-format=sha1", "--template=")
        git(repo, "add", "--all")
        git(repo, "commit", "-m", base_message)
        git(repo, "tag", base_tag)
        git(repo, "apply", str(source / "fix.patch"))
        git(repo, "commit", "-am", head_message)
        git(repo, "tag", head_tag)
        refs = tuple(git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}") for tag in (base_tag, head_tag))

        if not destination.exists():
            try:
                repo.rename(destination)
            except OSError:
                if not destination.exists():
                    raise
        existing = tuple(
            git(destination, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
            for tag in (base_tag, head_tag)
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


def prepare_shipping_harness(destination: Path, image: str, cache: Path, app_scaffold: Path) -> None:
    checkout = ROOT / "harness/checkout"
    shipping = ROOT / "harness/shipping"
    names = ("package.json", "package-lock.json", "playwright.config.cjs", "reporter.cjs", "wait-for-app.cjs")
    inputs = [checkout / name for name in names] + [shipping / "shipping.spec.cjs"]
    files = {source.name: source.read_bytes() for source in inputs}
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        digest.update(name.encode() + b"\0" + hashlib.sha256(data).digest())
    snapshot = destination.with_name(f"{destination.name}-{digest.hexdigest()}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="harness-", dir=destination.parent) as temp:
        staged = Path(temp) / "harness"
        staged.mkdir()
        for name, data in files.items():
            (staged / name).write_bytes(data)
        try:
            staged.rename(snapshot)
        except OSError:
            if not snapshot.is_dir():
                raise
            if {path.name for path in snapshot.iterdir()} != files.keys():
                raise ValueError(f"The generated shipping harness contains unexpected files at {snapshot}.")
            for name, data in files.items():
                existing = snapshot / name
                if not existing.is_file() or existing.read_bytes() != data:
                    raise ValueError(f"The generated shipping harness differs at {existing}.")
        warm_cache(image, cache, app_scaffold, snapshot)
        # The profile resolves this link before copying the harness for a comparison.
        link = Path(temp) / "active"
        link.symlink_to(snapshot.name, target_is_directory=True)
        link.replace(destination)


def prepare(fixture: str) -> None:
    profile_path = ROOT / "profiles" / f"{fixture}.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    repo = (profile_path.parent / profile["repository"]).resolve()
    cache = (profile_path.parent / profile["npm_cache"]).resolve()
    harness = Path(os.path.abspath(profile_path.parent / profile["harness"]))
    app_scaffold = ROOT / "fixtures/checkout/app"
    image = profile["runner_image"]
    base, head = fixture_commits(repo, fixture)
    if fixture == "shipping":
        prepare_shipping_harness(harness, image, cache, app_scaffold)
    else:
        warm_cache(image, cache, app_scaffold, harness)
    print(json.dumps({"repo": str(repo), "base": base, "head": head}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provision an owned BuildVerify fixture and its npm cache.")
    parser.add_argument("fixture", choices=COMMIT_MESSAGES)
    prepare(parser.parse_args().fixture)
