# Ordered implementation backlog

**Status:** all tasks are `NOT_STARTED` until Phase 0 verifies actual repo content. Priorities reflect PRD dependencies, not dates. Tasks may be already done; mark `VERIFIED_EXISTING` **only with file paths and test evidence**.

Task states: `NOT_STARTED`, `BLOCKED`, `IN_PROGRESS`, `IN_REVIEW`, `DONE_VERIFIED`, `VERIFIED_EXISTING`, `DEFERRED`.

| ID | Phase | Priority | Task and concrete deliverable | Depends on |
|---|---|---|---|---|
| BV-000 | 00 | P0 | Inspect git status, repo layout, dependencies, tests, CI, license | — |
| BV-001 | 00 | P0 | Safely run verified existing startup/build/test; record commands | 000 |
| BV-002 | 00 | P0 | Map original 5-stack/agent/sandbox claims to source files and test evidence | 000 |
| BV-003 | 00 | P0 | Create repo audit, status tracker, first ADRs, release risk list | 001,002 |
| BV-100 | 01 | P0 | TypeScript frontend strict config, route shell, accessible UI primitives | 003 |
| BV-101 | 01 | P0 | FastAPI typed app factory, health routes and standard errors | 003 |
| BV-102 | 01 | P0 | Postgres SQLAlchemy models + Alembic base migrations | 101 |
| BV-103 | 01 | P0 | Local demo identity, workspace membership, roles | 102 |
| BV-104 | 01 | P0 | Tenant-scoped repository/job storage and validation | 103 |
| BV-105 | 01 | P0 | Job CRUD, idempotency key, pagination | 104 |
| BV-106 | 01 | P0 | Generate/validate typed TS client from OpenAPI | 101,100 |
| BV-107 | 01 | P0 | Dashboard jobs list, create job form, auth/error/empty states | 105,106 |
| BV-108 | 01 | P0 | API/auth negative tests, migration+restart test, local compose | 102,107 |
| BV-200 | 02 | P0 | Typed job/step state machine and reason codes | 108 |
| BV-201 | 02 | P0 | Steps/attempts/events/outbox DB tables and transaction helpers | 200 |
| BV-202 | 02 | P0 | Redis Streams consumer group, publisher, lease management | 201 |
| BV-203 | 02 | P0 | Worker CAS fencing, XACK-after-commit, stale reclaim, retry/backoff | 202 |
| BV-204 | 02 | P0 | FakeStepHandler for success/transient/permanent/crash behaviors | 203 |
| BV-205 | 02 | P0 | SSE auth/replay with event sequence, reconnecting frontend | 201,107 |
| BV-206 | 02 | P0 | Cancel/timeout/retry/dead-letter logic and API | 203 |
| BV-207 | 02 | P0 | Chaos tests for old lease, duplicate message, ACK failure, Redis outage | 204,206 |
| BV-300 | 03 | P0 | ModelAdapter + deterministic mock and structured output validation | 207 |
| BV-301 | 03 | P0 | Canonical plan schema, plan hash and approval binding | 300 |
| BV-302 | 03 | P0 | Repo indexing/search/read allowed tool set | 301 |
| BV-303 | 03 | P0 | Safe apply-patch + canonical path/symlink checks | 302 |
| BV-304 | 03 | P0 | Policy engine and tool authorization by role/scope | 303 |
| BV-305 | 03 | P0 | Token and fixed-point cost budgets, phase limits | 300,304 |
| BV-306 | 03 | P0 | Developer patch attempt + review step, typed results | 301,304 |
| BV-307 | 03 | P0 | Prompt-injection and policy-negative tests, invalid plan/budget tests | 306 |
| BV-308 | 03 | P1 | Real provider behind adapter with explicit data consent and secret storage | 307 |
| BV-400 | 04 | P0 | RunnerProvider mocks and authenticated gateway contract | 307 |
| BV-401 | 04 | P0 | Provision truly isolated worker host/sandbox, constraints and cleanup | 400 |
| BV-402 | 04 | P0 | Immutable base checkout, locked test oracle and fingerprint manifest | 401 |
| BV-403 | 04 | P0 | Deterministic fixture projects FX-01 and FX-02 | 402 |
| BV-404 | 04 | P0 | Baseline reproduction stage, INCONCLUSIVE behavior | 403 |
| BV-405 | 04 | P0 | Patch stage and locked oracle test rerun with scope checks | 404 |
| BV-406 | 04 | P0 | Playwright 3-engine config, test JSON/JUnit, traces/screenshots | 403 |
| BV-407 | 04 | P0 | Browser matrix storage, error categories and retry metadata | 406,405 |
| BV-408 | 04 | P0 | Runner isolation/timeout/security-negative tests on disposable machine | 401,407 |
| BV-409 | 04 | P0 | Vertical slice demo fixture: base fails, patch passes, tests retained | 408 |
| BV-500 | 05 | P1 | Artifact storage adapter, hash upload, private access and expiry | 409 |
| BV-501 | 05 | P1 | Receipt schema, canonical JSON, receipt status rules | 500 |
| BV-502 | 05 | P1 | Receipt JSON/Markdown export and hash verifier CLI | 501 |
| BV-503 | 05 | P1 | QA matrix frontend, evidence links and before/after comparison | 500,502 |
| BV-504 | 05 | P1 | Approval/dialog UX, diff viewer, consistent stream reconnection | 503 |
| BV-505 | 05 | P1 | Tamper, private-artifact, skipped-tests and schema tests | 502,504 |
| BV-600 | 06 | P1 | GitHub App installation, minimal scopes, repo allowlist and auth state | 505 |
| BV-601 | 06 | P1 | Signed webhook validation, dedupe and outbox enqueue | 600 |
| BV-602 | 06 | P1 | Approval with exact patch+plan+repo+base hash and expiry | 601 |
| BV-603 | 06 | P1 | Branch push + idempotent draft PR with receipt links | 602 |
| BV-604 | 06 | P1 | API failure reconciliation to prevent duplicate branch/PR | 603 |
| BV-605 | 06 | P1 | Integration tests: scope, role, invalid signature, duplicate webhook/PR | 604 |
| BV-700 | 07 | P1 | OpenTelemetry spans + correlation and structured safe logs | 605 |
| BV-701 | 07 | P1 | Metrics: queue lag, attempts, browser durations, token/cost | 700 |
| BV-702 | 07 | P1 | CI matrix lint/type/unit/integration and deterministic Playwright | 701 |
| BV-703 | 07 | P1 | Security scans, dependency lock pinning, source-license review | 702 |
| BV-704 | 07 | P1 | Docker/dev setup + separated runner deployment and mock-only public mode | 703 |
| BV-705 | 07 | P1 | Chaos/reliability/load test report with machine specs + actual metrics | 704 |
| BV-706 | 07 | P1 | Runbooks, status docs, architecture diagram, demo video script | 705 |
| BV-800 | 08 | P2 | Controlled reruns and flaky candidate classifier with confidence/sample N | 706 |
| BV-801 | 08 | P2 | Failure signature clustering with independently labeled fixtures | 800 |
| BV-802 | 08 | P2 | Screenshot baseline approval and visual diff UI | 706 |
| BV-803 | 08 | P2 | Axe accessibility suite and report | 706 |
| BV-804 | 08 | P2 | Lighthouse budget tracking and baseline variations | 706 |
| BV-805 | 08 | P2 | Test prioritization algorithm with mandatory oracle inclusion | 801 |
| BV-806 | 08 | P2 | QA analytics accuracy/speed measurement report | 805,802,803,804 |
| BV-807 | 08 | P2 stretch | Privacy-masked rrweb/HAR session-to-reviewed-test proposal | 706 |
| BV-808 | 08 | P2 stretch | Mutation testing runner for selected small TS modules + advisory score | 706 |
| BV-900 | 09 | P2 | App-generation templates and structured generator manifest | 706 |
| BV-901 | 09 | P2 | App export with generated tests + reproducible README | 900 |
| BV-902 | 09 | P2 | Optional compatible WebContainers preview, graceful fallback | 901 |
| BV-903 | 09 | P2 | Lightweight repo map/context selection, token usage comparison | 706 |
| BV-904 | 09 | P2 | Single-agent vs multi-agent controlled A/B benchmark | 903,901 |
| BV-905 | 09 | P2 | Verified benchmark report, limitations and honest resume bullets | 904 |
| BV-A00 | 10 | P3 | Choose only one: remote QA or Temporal or hardened sandbox or scale | 706 |
| BV-A01 | 10 | P3 | Prototype selected adapter and write measured ADR | A00 |
| BV-A02 | 10 | P3 | Re-run V1 regression suite and document hard limits | A01 |

## Backlog issue template
```markdown
# [BV-XXX] Short task name
Parent PRD: PRD-XX
Priority: P0/P1/P2/P3
Depends on: BV-...

## User-visible outcome
One coherent capability.

## Scope
Included:
Not included:

## Design proposal and contracts
Affected packages/API/schema/event versions:
Security boundaries / data exposure:
Alternatives considered:

## Acceptance tests
- [ ] Happy path
- [ ] Failure path
- [ ] Auth/permissions (if applicable)
- [ ] Retry/idempotency (if applicable)
- [ ] Observability evidence

## Definition of done
- [ ] Correct implementation
- [ ] Actual commands and test results recorded
- [ ] Docs/migrations updated
- [ ] No unsupported capability claims
- [ ] Status tracker updated
```

## Personal study prompts to preserve engineering ownership
For every serious PR, be able to answer: *What alternatives did I reject? What invariant does this component enforce? Where can it race? What breaks if the network dies? What is the computational/operational complexity? What does an attacker control? What do the negative tests demonstrate?*

## Milestone publishing advice
- **First useful demo:** BV-409 + BV-205 (working end-to-end patch, QA + UI events).
- **Strong resume project:** through BV-706 (auditable, tested, secure-by-design V1).
- **Research / standout differentiation:** selected BV-800+ experiments with honest results.
