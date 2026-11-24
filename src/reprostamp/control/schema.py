from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


RunState = Literal["queued", "running", "cancelling", "cancelled", "completed", "incomplete", "blocked"]
Verdict = Literal["VERIFIED", "FAILED", "INCONCLUSIVE", "POLICY_BLOCKED"]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=256, pattern=r"^[^\s\x00-\x1f\x7f]+$")]
RegistrationId = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Engine = Literal["chromium", "firefox", "webkit"]
Side = Literal["base", "head"]


class Login(BaseModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=512)]


class Session(BaseModel):
    csrf_token: str


class RepositoryChoice(BaseModel):
    id: str
    label: str


class ProfileChoice(RepositoryChoice):
    repo_id: str
    base: str
    head: str


class Registry(BaseModel):
    repositories: list[RepositoryChoice]
    profiles: list[ProfileChoice]


class NewRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_id: RegistrationId
    profile_id: RegistrationId
    base_ref: Ref
    head_ref: Ref


class NewCaseReplay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Engine
    side: Side
    number: Literal[1, 2]
    case_id: RegistrationId


class ReplaySelection(NewCaseReplay):
    model_config = ConfigDict(extra="ignore")

    receipt_sha: str
    commit: str


class CaseReplayLink(BaseModel):
    id: UUID
    state: RunState
    replay: ReplaySelection
    created_at: datetime


class ReplaySummary(BaseModel):
    classification: Literal["consistent_failure", "suspected_flaky", "infrastructure_failure",
                            "insufficient_evidence", "passed_on_replay"] | None
    sample_size: int
    passed: int
    assertion_failed: int
    infrastructure_failure: int


class FailureReceipt(BaseModel):
    run_id: UUID
    receipt_sha: str
    expired: bool
    browsers: list[Engine]
    count: int


class FailureGroup(BaseModel):
    kind: Literal["application_assertion", "infrastructure_failure"]
    case_id: str | None
    assertion: str | None
    expected: str | None
    application_location: str | None
    reason: str | None
    first_seen: datetime
    last_seen: datetime
    browsers: list[Engine]
    count: int
    receipts: list[FailureReceipt]


class ReviewRoute(BaseModel):
    id: RegistrationId
    path: str
    ready: str
    visual_required: bool
    accessibility_required: bool


class ReviewPlan(BaseModel):
    engine: Engine
    routes: list[ReviewRoute]


class Plan(BaseModel):
    engines: list[str]
    case_ids: list[str]
    review: ReviewPlan | None = None


class Assertion(BaseModel):
    id: str
    actual: str | None
    expected: str


class Case(BaseModel):
    case_id: str
    status: str
    playwright_status: str
    duration_ms: int
    assertion: Assertion | None
    artifacts: dict[str, str]
    detail: str | None
    application_location: str | None = None


class BrowserBuild(BaseModel):
    version: str
    platform: str


class NewVisualApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_sha: Sha256
    screenshot_sha256: Sha256


class VisualBinding(BaseModel):
    route_id: RegistrationId
    engine: Engine
    browser_build: BrowserBuild
    commit: str
    profile_sha256: Sha256
    screenshot_sha256: Sha256


class VisualApproval(BaseModel):
    binding: VisualBinding
    run_id: UUID
    receipt_sha: Sha256
    accepted_by: Literal["owner"]
    accepted_at: datetime


class VisualReview(BaseModel):
    required: bool
    status: Literal["changed", "unchanged", "approved", "unavailable"]
    detail: str | None
    changed_pixels: int | None
    artifacts: dict[str, str]
    binding: VisualBinding | None
    applied_approval: VisualApproval | None


class AxeFinding(BaseModel):
    rule: str
    impact: Literal["minor", "moderate", "serious", "critical"] | None
    target: str


class AccessibilityReview(BaseModel):
    required: bool
    status: Literal["regression", "passed", "unavailable"]
    detail: str | None
    axe_version: str | None
    findings: list[AxeFinding]


class RouteReview(BaseModel):
    route_id: RegistrationId
    path: str
    engine: Engine
    browser_build: BrowserBuild | None
    profile_sha256: Sha256
    visual: VisualReview
    accessibility: AccessibilityReview


class AttemptResult(BaseModel):
    duration_ms: int
    reason: str | None
    detail: str | None
    cases: list[Case]
    logs: dict[str, str]
    browser_build: BrowserBuild | None


class Attempt(BaseModel):
    fence: int
    engine: str
    side: Side
    number: Annotated[int, Field(ge=1, le=5)]
    state: Literal["running", "completed", "incomplete", "interrupted"]
    result: AttemptResult | None


class Artifact(BaseModel):
    id: UUID
    kind: Literal["receipt", "trace", "screenshot", "log"]
    path: str
    size: int
    sha256: str


class EngineVerdict(BaseModel):
    name: Verdict
    reason: str
    detail: str


class RunSummary(BaseModel):
    id: UUID
    request: NewRun
    base_sha: str
    head_sha: str
    state: RunState
    fence: int
    plan: Plan
    verdict: Verdict | None
    reason: str | None
    detail: str | None
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    expired: bool | None
    receipt_sha: str | None
    superseded_at: datetime | None = None
    source_run_id: UUID | None = None
    replay: ReplaySelection | None = None


class RunDetail(RunSummary):
    attempts: list[Attempt]
    artifacts: list[Artifact]
    engine_verdicts: dict[str, EngineVerdict]
    replay_summary: ReplaySummary | None = None
    case_replays: list[CaseReplayLink]
    reviews: list[RouteReview]
    visual_approvals: list[VisualApproval]


class RunEvent(BaseModel):
    seq: int
    kind: str
    data: dict
    created_at: datetime


class Timeline(BaseModel):
    events: list[RunEvent]
    terminal: bool
