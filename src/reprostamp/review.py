import json
import re
import shutil
import stat
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from .integrity import hash_file
from .profile import Profile, ReviewRoute
from .runner import Attempt, BrowserBuild
from .verdict import Verdict


REVIEW_FILES = {"base": "baseline.png", "head": "candidate.png", "diff": "diff.png"}
MAX_FINDINGS = 200
MAX_PNG_BYTES = 32 * 1024 * 1024
AXE_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


@dataclass(frozen=True)
class Finding:
    rule: str
    target: str
    impact: str | None

    def __post_init__(self):
        if (not isinstance(self.rule, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", self.rule)
            or not isinstance(self.target, str) or not 1 <= len(self.target) <= 1024
            or self.impact not in (None, "minor", "moderate", "serious", "critical")):
            raise ValueError("Invalid axe rule, target, or impact.")


def findings_from_report(value: list) -> frozenset[Finding]:
    if not isinstance(value, list) or len(value) > MAX_FINDINGS:
        raise ValueError(f"Expected at most {MAX_FINDINGS} axe findings per route.")
    return frozenset(Finding(**finding) for finding in value)


@dataclass(frozen=True)
class Capture:
    directory: Path
    axe_version: str
    routes: dict[str, dict]


def read_capture(directory: Path, build: BrowserBuild, engine: str, routes: set[str]) -> Capture:
    report = directory / "review.json"
    metadata = report.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 3 * 1024 * 1024:
        raise ValueError("The review report must be a regular file within its size limit.")
    data = json.loads(report.read_text(encoding="utf-8"))
    browser = data["browser"]
    if (not isinstance(browser, dict) or browser.keys() != {"engine", "version", "platform"}
            or BrowserBuild.from_report(browser, engine) != build):
        raise ValueError("The review browser build differs from the functional attempt.")
    version = data["axe_version"]
    if not isinstance(version, str) or not AXE_VERSION.fullmatch(version):
        raise ValueError("The harness did not record a valid axe version.")
    entries = {route["id"]: route for route in data["routes"]}
    if entries.keys() != routes or len(entries) != len(data["routes"]):
        raise ValueError("The harness did not record exactly the configured review routes.")
    return Capture(directory, version, entries)


def screenshot(capture: Capture, route: ReviewRoute, dimensions: tuple[int, int]) -> tuple[Path, str, Image.Image]:
    observation = capture.routes[route.id]
    if observation["visual_error"] is not None:
        raise ValueError(str(observation["visual_error"]))
    path = (capture.directory / f"review-{route.id}.png").resolve()
    if not path.is_relative_to(capture.directory.resolve()) or not path.is_file() or path.stat().st_size > MAX_PNG_BYTES:
        raise ValueError("Expected a screenshot file within the evidence directory and size limit.")
    with path.open("rb") as file:
        digest = hash_file(file)
        file.seek(0)
        with Image.open(file, formats=("PNG",)) as image:
            if image.size != dimensions:
                raise ValueError(f"The screenshot dimensions must be {dimensions[0]} × {dimensions[1]}.")
            return path, digest, image.convert("RGB")


def summarize_visual(route: ReviewRoute, captures: dict[str, list[Capture]], dimensions: tuple[int, int],
                     out: Path, binding: dict, approvals: list[dict]) -> dict:
    summary = {"required": route.visual_required, "status": "unavailable", "detail": None,
               "changed_pixels": None, "artifacts": {}, "binding": None, "applied_approval": None}
    images = {}
    try:
        for side, attempts in captures.items():
            first, second = (screenshot(capture, route, dimensions) for capture in attempts)
            if first[1] != second[1]:
                raise ValueError(f"The {side} screenshot changed between attempts.")
            images[side] = first
    except (KeyError, OSError, TypeError, ValueError, Image.DecompressionBombError) as error:
        summary["detail"] = str(error)[:512]
        return summary

    difference = ImageChops.difference(images["base"][2], images["head"][2])
    red, green, blue = difference.split()
    mask = ImageChops.lighter(ImageChops.lighter(red, green), blue).point([0] + [255] * 255)
    changed = mask.histogram()[255]
    folder = out / "review" / binding["engine"] / route.id
    context = Image.blend(ImageOps.grayscale(images["base"][2]).convert("RGB"),
                          Image.new("RGB", dimensions, "white"), 0.75)
    context.paste((214, 34, 86), mask=mask)
    try:
        folder.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder.parent) as temp:
            staged = Path(temp) / route.id
            staged.mkdir()
            for side in captures:
                shutil.copyfile(images[side][0], staged / REVIEW_FILES[side])
            diff_file = staged / REVIEW_FILES["diff"]
            context.save(diff_file, format="PNG")
            if diff_file.stat().st_size > MAX_PNG_BYTES:
                raise OSError("The pixel diff exceeds its size limit.")
            staged.rename(folder)
    except OSError as error:
        summary["detail"] = f"Could not export the screenshot comparison. {error}"[:512]
        return summary
    summary.update(status="changed" if changed else "unchanged", changed_pixels=changed,
                   artifacts={role: (folder / name).relative_to(out).as_posix() for role, name in REVIEW_FILES.items()})
    if changed:
        binding = {**binding, "screenshot_sha256": images["head"][1]}
        approval = next((item for item in approvals if item["binding"] == binding), None)
        summary.update(binding=binding, applied_approval=approval, status="approved" if approval else "changed")
    return summary


def summarize_accessibility(route: ReviewRoute, captures: dict[str, list[Capture]]) -> dict:
    summary = {"required": route.accessibility_required, "status": "unavailable", "detail": None,
               "axe_version": None, "findings": []}
    try:
        versions = {capture.axe_version for attempts in captures.values() for capture in attempts}
        if len(versions) != 1:
            raise ValueError("The axe version changed between attempts.")
        results = {}
        for side, attempts in captures.items():
            observations = []
            for capture in attempts:
                entry = capture.routes[route.id]
                if entry["accessibility_error"] is not None:
                    raise ValueError(str(entry["accessibility_error"]))
                observations.append(findings_from_report(entry["findings"]))
            if observations[0] != observations[1]:
                raise ValueError(f"The {side} axe findings changed between attempts.")
            results[side] = observations[0]
        added = sorted(results["head"] - results["base"], key=lambda item: (item.rule, item.target, item.impact or ""))
        summary.update(status="regression" if added else "passed", axe_version=versions.pop(),
                       findings=[asdict(item) for item in added])
    except (KeyError, OSError, TypeError, ValueError) as error:
        summary["detail"] = str(error)[:512]
    return summary


def collect_reviews(profile: Profile, attempts: list[Attempt], inputs: dict, head: str,
                    workspace: Path, out: Path, approvals: list[dict]) -> list[dict]:
    plan = profile.review
    if plan is None:
        return []
    samples = {side: [item for item in attempts if item.engine == plan.engine and item.side == side]
               for side in ("base", "head")}
    captures = {}
    build = None
    detail = None
    try:
        if any(len(items) != 2 or any(item.status != "completed" for item in items) for items in samples.values()):
            raise ValueError("The review requires two completed browser attempts per commit.")
        builds = {item.browser_build for items in samples.values() for item in items}
        if len(builds) != 1 or None in builds or next(iter(builds)).platform != inputs["runner_platform"]:
            raise ValueError("The review requires a consistent browser build and runner platform.")
        build = builds.pop()
        ids = {route.id for route in plan.routes}
        captures = {side: [read_capture(workspace / f"{plan.engine}-{side}-{item.number}", build, plan.engine, ids)
                           for item in items] for side, items in samples.items()}
    except (KeyError, OSError, TypeError, ValueError) as error:
        detail = ("The review harness did not produce a report for every attempt."
                  if isinstance(error, FileNotFoundError) else str(error)[:512])
    reviews = []
    dimensions = (profile.browser.viewport_width, profile.browser.viewport_height)
    for route in plan.routes:
        browser = asdict(build) if build else None
        if detail is None:
            binding = {"route_id": route.id, "engine": plan.engine, "browser_build": browser,
                       "commit": head, "profile_sha256": inputs["profile_sha256"]}
            visual = summarize_visual(route, captures, dimensions, out, binding, approvals)
            accessibility = summarize_accessibility(route, captures)
        else:
            visual = {"required": route.visual_required, "status": "unavailable", "detail": detail,
                      "changed_pixels": None, "artifacts": {}, "binding": None, "applied_approval": None}
            accessibility = {"required": route.accessibility_required, "status": "unavailable", "detail": detail,
                             "axe_version": None, "findings": []}
        reviews.append({"route_id": route.id, "path": route.path, "engine": plan.engine, "browser_build": browser,
                        "profile_sha256": inputs["profile_sha256"],
                        "visual": visual, "accessibility": accessibility})
    return reviews


def review_verdict(functional: Verdict, reviews: list[dict]) -> Verdict:
    if functional.name != "INCONCLUSIVE":
        for review in reviews:
            for kind in ("visual", "accessibility"):
                check = review[kind]
                if check["required"] and check["status"] == "unavailable":
                    return Verdict("INCONCLUSIVE", f"required_{kind}_unavailable",
                                   f"{review['path']} [{review['engine']}]: {check['detail']}")
    if functional.name == "VERIFIED":
        for review in reviews:
            if review["accessibility"]["required"] and review["accessibility"]["status"] == "regression":
                return Verdict("FAILED", "required_accessibility_regression",
                               f"New axe findings appeared on {review['path']} [{review['engine']}].")
            if review["visual"]["required"] and review["visual"]["status"] == "changed":
                return Verdict("FAILED", "required_visual_change",
                               f"The screenshot of {review['path']} [{review['engine']}] changed and needs approval.")
    return functional
