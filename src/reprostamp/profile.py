import fnmatch
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
IMAGE = re.compile(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}\Z")
ENGINES = ("chromium", "firefox", "webkit")
REVIEW_PATH = re.compile(r"/(?!/)[!-~]{0,511}\Z")
MAX_REVIEW_ROUTES = 8
PROTECTED_FILES = {
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
    "pnpm-lock.yaml", "bun.lock", "bun.lockb", ".npmrc", ".gitmodules",
    ".gitattributes",
}
PROTECTED_DIRS = {"test", "tests", "__tests__", "harness", "playwright", "node_modules"}


class PolicyError(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


@dataclass(frozen=True)
class ExpectedFailure:
    case_id: str
    assertion_id: str
    baseline_actual: str


@dataclass(frozen=True)
class BrowserSettings:
    seed: int = 42
    viewport_width: int = 1100
    viewport_height: int = 800
    locale: str = "en-US"
    timezone: str = "UTC"


@dataclass(frozen=True)
class ReviewRoute:
    id: str
    path: str
    ready: str
    visual_required: bool = False
    accessibility_required: bool = False


@dataclass(frozen=True)
class ReviewPlan:
    engine: str
    routes: tuple[ReviewRoute, ...]


def review_plan(data: dict, engines: Sequence[str]) -> ReviewPlan:
    if not isinstance(data, dict) or data.keys() != {"engine", "routes"} or data["engine"] not in engines:
        raise ValueError("Set the review engine to one of the profile's required browsers.")
    if not isinstance(data["routes"], list) or not 1 <= len(data["routes"]) <= MAX_REVIEW_ROUTES:
        raise ValueError(f"Configure between 1 and {MAX_REVIEW_ROUTES} review routes.")
    routes = tuple(ReviewRoute(**item) for item in data["routes"])
    seen = set()
    for route in routes:
        if not isinstance(route.id, str) or not CASE_ID.fullmatch(route.id) or route.id.lower() in seen:
            raise ValueError("Use distinct review route IDs containing letters, numbers, dots, underscores, or hyphens.")
        seen.add(route.id.lower())
        if not isinstance(route.path, str) or not REVIEW_PATH.fullmatch(route.path) or "\\" in route.path:
            raise ValueError("Review routes must be root-relative application URLs.")
        if not isinstance(route.ready, str) or not route.ready.strip() or len(route.ready) > 512:
            raise ValueError("Set a visible Playwright readiness selector for each review route.")
        if any(type(value) is not bool for value in (route.visual_required, route.accessibility_required)):
            raise ValueError("Required review settings must be booleans.")
    return ReviewPlan(data["engine"], routes)


@dataclass(frozen=True)
class Profile:
    harness: Path
    npm_cache: Path
    runner_image: str
    expected_failure: ExpectedFailure
    required_regressions: tuple[str, ...]
    editable_paths: tuple[str, ...]
    timeout_seconds: int
    engines: tuple[str, ...]
    browser: BrowserSettings
    review: ReviewPlan | None = None

    @property
    def case_ids(self) -> frozenset[str]:
        return frozenset((self.expected_failure.case_id, *self.required_regressions))

    def allows(self, path: str) -> bool:
        parts = PurePosixPath(path.lower()).parts
        filename = parts[-1]
        return (
            not PROTECTED_DIRS.intersection(parts[:-1])
            and filename not in PROTECTED_FILES
            and not re.search(r"\.(?:spec|test)\.", filename)
            and not filename.startswith(("playwright.config.", ".env"))
            and any(fnmatch.fnmatchcase(path, pattern) for pattern in self.editable_paths)
        )


def load_profile(path: Path, repo: Path) -> Profile:
    if path.is_relative_to(repo):
        raise PolicyError("profile_inside_repository", "The profile must be outside the application repository.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("The profile must contain a JSON object.")

        def nonempty_string(data: dict, key: str) -> str:
            value = data[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a nonempty string.")
            return value

        def strings(key: str) -> tuple[str, ...]:
            value = data[key]
            if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
                raise ValueError(f"{key} must be a nonempty list of strings.")
            return tuple(value)

        approved_repo = (path.parent / nonempty_string(data, "repository")).resolve()
        harness = (path.parent / nonempty_string(data, "harness")).resolve()
        npm_cache = (path.parent / nonempty_string(data, "npm_cache")).resolve()
        image = nonempty_string(data, "runner_image")
        if not IMAGE.fullmatch(image):
            raise ValueError("runner_image must be pinned with a SHA-256 digest.")

        failure = data["expected_failure"]
        if not isinstance(failure, dict):
            raise ValueError("expected_failure must be an object.")
        expected = ExpectedFailure(*(nonempty_string(failure, key) for key in (
            "case_id", "assertion_id", "baseline_actual",
        )))
        regressions = strings("required_regressions")
        case_ids = (expected.case_id, *regressions)
        if len({case.lower() for case in case_ids}) != len(case_ids) or any(not CASE_ID.fullmatch(case) for case in case_ids):
            raise ValueError("Use distinct case IDs containing letters, numbers, dots, underscores, or hyphens.")

        patterns = strings("editable_paths")
        if any(not pattern.startswith("src/") or ".." in pattern.split("/") for pattern in patterns):
            raise ValueError("Editable globs must be rooted under src/.")
        timeout = data["timeout_seconds"]
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise ValueError("timeout_seconds must be an integer between 1 and 120.")
        engines = strings("engines") if "engines" in data else ("chromium",)
        if len(set(engines)) != len(engines) or any(engine not in ENGINES for engine in engines):
            raise ValueError("Choose distinct engines from chromium, firefox, and webkit.")
        settings = BrowserSettings(**data.get("browser", {}))
        if type(settings.seed) is not int or not 0 <= settings.seed < 2**32:
            raise ValueError("The browser seed must be an unsigned 32-bit integer.")
        for dimension in (settings.viewport_width, settings.viewport_height):
            if type(dimension) is not int or not 1 <= dimension <= 4096:
                raise ValueError("Browser viewport dimensions must be integers between 1 and 4096.")
        for setting in ("locale", "timezone"):
            nonempty_string(vars(settings), setting)
        review = review_plan(data["review"], engines) if data.get("review") is not None else None
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise PolicyError("invalid_profile", str(error)) from error

    if approved_repo != repo:
        raise PolicyError("repository_not_approved", "The repository path does not match the profile registration.")
    if harness.is_relative_to(repo) or repo.is_relative_to(harness) or npm_cache.is_relative_to(repo):
        raise PolicyError("inputs_inside_repository", "Keep the harness and dependency cache outside the application tree.")

    return Profile(harness, npm_cache, image, expected, regressions, patterns, timeout, engines, settings, review)
