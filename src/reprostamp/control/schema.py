from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints


RunState = Literal["queued", "running", "cancelling", "cancelled", "completed", "incomplete", "blocked"]
Verdict = Literal["VERIFIED", "FAILED", "INCONCLUSIVE", "POLICY_BLOCKED"]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=256, pattern=r"^[^\s\x00-\x1f\x7f]+$")]
RegistrationId = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]


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


class Plan(BaseModel):
    engines: list[str]
    case_ids: list[str]


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


class BrowserBuild(BaseModel):
    version: str
    platform: str


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
    side: Literal["base", "head"]
    number: Literal[1, 2]
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


class RunDetail(RunSummary):
    attempts: list[Attempt]
    artifacts: list[Artifact]
    engine_verdicts: dict[str, EngineVerdict]


class RunEvent(BaseModel):
    seq: int
    kind: str
    data: dict
    created_at: datetime


class Timeline(BaseModel):
    events: list[RunEvent]
    terminal: bool
