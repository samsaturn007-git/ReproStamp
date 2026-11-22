# Phase-by-phase engineering PRDs

**Usage:** Implement **one PRD at a time**, starting with PRD-00. Each PRD has a single working outcome, explicit acceptance criteria, negative tests, and an exit gate. Source repository was redacted; Phase 0 must determine actual code status.

Priority legend: **P0 required for Evidence MVP**, **P1 required for portfolio-quality V1**, **P2 standout extensions**, **P3 optional research**. A phase can be split into several PRs. Do not bypass a gate to display a polished but nonfunctional dashboard.

---

# PRD-00 — Existing repository audit, recovery and architecture decision (P0)

**Objective:** Safely continue an existing project if one exists; otherwise establish and document a clean greenfield skeleton. Avoid destructive assumptions about current functionality.

**User story:** As the owner, I want an objective audit of what already works so the coding agent can preserve and extend it without losing completed work.

**Required activities**
1. Identify git root, branch, working tree status and LICENSE; list top-level directory and package managers.
2. Inspect `package.json`, Python dependencies, README, CI workflows, Docker/compose, schema/migrations, API routes and test folders. Ask for repo URL only when repo truly unavailable to the coding environment; otherwise proceed on mounted files.
3. Run existing documented build/lint/test commands **only when safe**; do not execute untrusted code on host. Mark unrun items with reason.
4. Audit original claims: FastAPI, Next.js, Redis, PostgreSQL, WebSockets, agent roles, token budgets, WebContainers, retry policy, sandbox. Verify each as `implemented + tested`, `partial`, `stubbed`, `not found`, `unknown`.
5. Create feature gap table mapped to FR IDs and task IDs. Document existing defects, tech debt, security issues and integration stubs.
6. Decide adaptation vs greenfield by actual repo evidence; preserve stable, licensed components, avoid unnecessary architecture rewrite.
7. Create `docs/REPO_AUDIT.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/adr/ADR-001.md` etc. Update root README with true setup.

**Deliverables:** Audit table, architecture diagram of existing code, verified commands/results, prioritized changes, phase plan, initial task backlog statuses.

**Acceptance / negative tests:** Existing code unchanged except docs/test fixes explicitly agreed; no credentials output; no blanket delete; existing test results recorded accurately; all 'present' claims linked to files. Block adding runner or LLM before baseline audit.

**Exit gate:** Owner/agent can answer “what exists, what is stubbed, what should be done next, and what is the first safe PR?”

---

# PRD-01 — Product skeleton, identity, persistence and UX foundation (P0)

**Objective:** Build a minimal full-stack application with safe session handling, workspace scoping, a normalized database, and end-to-end typed API communication.

**Stories**
- US-101: I can start a local development stack and visit a functional dashboard.
- US-102: I can create/view a workspace and an allowlisted demo repository.
- US-103: I can submit a job specification with a selected test profile and hard budget cap.
- US-104: Another workspace member cannot read my run or artifacts.

**Work packages**
- Bootstrapped, locked dependency versions; implement Next.js strict TS frontend and FastAPI server with health checks.
- PostgreSQL, Alembic migration baseline; schema for users, workspaces, memberships, repositories and jobs; seed synthetic fixture repo.
- Session provider for dev (e.g., local test auth) behind interface; production OAuth/hosted credentials may be deferred. Never hardcode shared 'admin' token into shipped app.
- RBAC middleware and workspace-in-query restrictions; CSRF protection for cookie-backed mutating actions, secure cookies in hosted mode; rate limit plan.
- Pydantic request/response schemas and typed frontend client; standard error response; pagination.
- UI navigation, workspace chooser, jobs table, 'new run' form; genuine error states and keyboard focus.
- CI job for static type/lint/unit tests; `.env.example` with no live keys.

**Acceptance**
- `docker compose` or documented equivalent boots API, web and DB using synthetic data.
- POST then GET job returns persisted job; job present after API restart.
- No valid auth -> 401; wrong role -> 403; cross-workspace access -> 404 or 403 consistently without information disclosure.
- Invalid base SHA, budget, malformed issue or unsupported test profile -> 4xx validation error with stable code.
- One integration test proves migrations from blank DB and roll forward/rollback policy.
- No real LLM or GitHub write necessary.

**Deliverables:** Working UI/API skeleton; DB migrations; auth contract; seed fixtures; README startup; tests.  
**Dependencies:** PRD-00.  
**Interview skills:** API design, SQL indexing, auth, type safety, frontend architecture, transactional persistence.

---

# PRD-02 — Durable workflow engine and real-time job events (P0)

**Objective:** Demonstrate reliable distributed programming before delegating to AI agents.

**Stories**
- US-201: A submitted job enters a deterministic multi-step workflow and progresses visibly.
- US-202: A worker can die and restart without losing work or double-applying external effects.
- US-203: I can cancel, pause for approval and replay missed events after reconnect.

**Work packages**
- Write transition table with allowed states and terminal handling; optimistic locking via version fields.
- Create `steps`, `attempts`, `events`, `outbox`, `webhook_deliveries`, ledger tables and constraints.
- Implement outbox publisher: DB event + outbox same transaction; publish to Redis Streams; resume unpublished records.
- Worker consumer group: XREADGROUP, XACK after successful persistence, lease heartbeats, stale claim, bounded exponential retry/jitter, dead-letter state; outbox/worker message IDs.
- Implement `FakeStepHandler` that can deterministically succeed, fail transiently, fail permanently, sleep and simulate crash.
- SSE authorized stream with DB replay cursor `event_seq`; hydrate from DB then subscribe to live notifications; prevent gaps/dup order by sequence dedupe.
- UI timeline, attempt log, stable progress badges (based on actual state), retry/cancel with role checks.

**Acceptance**
- 100 synthetic jobs can be queued, consumed and reach expected final states on local test infrastructure; recorded machine and concurrency.
- Kill worker immediately after task lease or just before `XACK`, restart; every logical step has **at most one committed logical effect** while attempts may be >1.
- Duplicate `POST /jobs` with same workspace/idempotency key returns same job.
- Simulate DB commit succeeds but Redis ACK fails; no duplicate logical events/results.
- Simulate old worker awakening after lease taken by new worker; fencing prevents stale commit.
- SSE disconnect/reconnect returns all missing events in sequence without cross-tenant leakage.
- Cancellation, budget-exceeded and permanent-policy-denied states do not retry indefinitely.

**Deliverables:** Worker service with fake tasks, replayable event view, chaos tests and ADR comparing Redis Streams/Temporal.  
**Dependencies:** PRD-01.  
**Interview skills:** message delivery semantics, outbox, distributed leases, idempotency, concurrency and race conditions, observability.

---

# PRD-03 — Constrained planning, code editing and review agent (P0)

**Objective:** Turn a requirement into a structured, authorized patch without giving the model uncontrolled shell or network access.

**Stories**
- US-301: I can submit a requirement and receive a file-scoped plan with risks and estimated budget.
- US-302: I approve the plan by its immutable hash before editing begins.
- US-303: The agent can propose a small patch and receive specific reviewer feedback.

**Work packages**
- Define `ModelAdapter`, `AgentStep` and `ToolPolicy` interfaces; implement deterministic fixture/mock model first, real provider second.
- Planner receives known repo-map excerpts, issue description (labeled untrusted), project conventions and strict JSON schema; plans expected tests/allowed file scope.
- Store canonical plan hash; scope changes require reapproval; approve only signed-in permitted actor.
- Allowlisted tools: `list_files`, `search_text`, `read_file`, `apply_patch` (path canonicalization, symlink checks), `inspect_diff`. No raw arbitrary `exec` from LLM.
- Agent loop capped by model tokens/estimated cost/tool calls/diff size/attempts; persist step metrics and reason codes.
- Reviewer validates `git diff --check`, changed-path policies, dependencies, lockfiles, secret patterns and test expectations; human-visible rationale.
- Repo map P1 extension: track file tree/symbols/import paths and compute lightweight relevance scores; make indexing incremental with content-hash invalidation.

**Acceptance**
- Mock mode: given fixture issue, planner proposes allowed `src/**` patch, user approves, editor modifies correct file and reviewer approves/dismisses with deterministic result.
- Generated invalid JSON -> schema-retry bounded then recorded error, not arbitrary interpretation.
- Model asks to modify `.github/workflows/`, `.env`, secrets, independent oracle or outside directory -> policy denies and logs safe reason.
- Token exhaustion stops work in `BUDGET_EXHAUSTED` with useful partial artifacts.
- Reviewer catches unexpected dependency change and refuses to advance without human approval.
- Prompt injection from fixture issue cannot add new tools or permissions.

**Deliverables:** Controlled edit workflow with real authorization and mock/real LLM adapters, budget ledger, test suite.  
**Dependencies:** PRD-02.  
**Interview skills:** AI system design, prompt/context engineering, interfaces, policy enforcement, security, cost accounting.

---

# PRD-04 — Isolated execution, baseline reproduction and 3-engine QA (P0)

**Objective:** Establish the product's central proof: baseline failure and patched pass under the **same locked oracle test**, with browser traces.

**Stories**
- US-401: The platform reproduces a bug against an immutable base SHA.
- US-402: It executes the patch using a constrained runner and tests browser behavior.
- US-403: It reports all 3 browser engines honestly with evidence, skips and failure reasons.

**Work packages**
- Implement `RunnerProvider` with `MockRunner` and a *separately hosted* isolation-backed runner provider; never execute untrusted workloads within FastAPI/worker host.
- Runner creates per-job workspace, checks out immutable base SHA using cached/allowlisted source and pinned deps; test oracles provided outside agent-editable tree.
- Run locked reproduction before patch. Persist failure signature, exit status, test case ID, environment and failure artifacts; mark `INCONCLUSIVE` if baseline cannot reproduce.
- Run agent patch in isolated cloned workspace; verify path restrictions again; refuse oracle modifications.
- Playwright config for Chromium, Firefox, WebKit in pinned versions; output JUnit/JSON, traces, screenshots and console/network errors with redaction.
- Fixed timeouts, max processes, memory/CPU/disk quotas, non-root, no host privileges, restricted network, known test command set and cleanup on abort.
- Compute test matrix and classify infrastructure errors separately from test assertion failures.
- Optional preview via WebContainers if code is compatible and browser requirements permit; do not make it core runner or cloud isolation claim.

**Acceptance**
- Controlled fixture includes: (A) deterministic baseline failure + patch passing all three engines, (B) intentional browser-specific failure, (C) flaky timing case, (D) runner infrastructure failure.
- For A, baseline oracle fails; after patch same unchanged oracle passes; existing regression suite passes.
- For B, matrix captures at least one engine-specific failure without calling the job `VERIFIED`.
- For C, first retry cannot silently erase failure; show attempt history.
- For D, status `INCONCLUSIVE` or retryable infra failure, not product bug.
- Artifact includes runtime image digest, browser versions, base/target SHA and test command manifest.
- A prohibited host-path read, privileged command and outbound network attempt is blocked by enforced environment/policy; security tests executed on an **isolated disposable test machine**, not a developer's primary host.
- Runner terminates and cleans up after timeouts and cancelled jobs.

**Deliverables:** End-to-end reproducible patch/test demo, 3-browser QA engine, runner isolation and negative tests.  
**Dependencies:** PRD-03.  
**Interview skills:** secure execution, browser testing, subprocess/resource control, cross-browser compatibility, test harness design.

---

# PRD-05 — Verification Receipt, artifacts and professional QA dashboard (P1)

**Objective:** Turn raw agent and test logs into auditable, usable, differentiated engineering evidence.

**Stories**
- US-501: As reviewer, I can inspect base vs patch evidence and distinguish assertions from environment failures.
- US-502: I can download a machine-readable receipt and repeat the verification with declared versions.
- US-503: Reconnected browser UI resumes streaming without lost events.

**Work packages**
- Introduce S3-compatible artifact store (MinIO locally), content-addressed keys, SHA256 digest check, metadata in Postgres, signed read URL per authenticated request.
- Build deterministic receipt renderer from persisted test/run/approval data. Status rules are code, not LLM prompt. Schema version and canonical JSON algorithm.
- Capture baselines vs patched tests, browser matrix, failure stack traces, screenshot/trace links, skipped cases with reasons, immutable commit+diff hashes.
- Implement QA dashboard: filters by browser/failure, evidence tab, compact diff view, per-attempt timeline, approve/cancel status.
- Receipt export JSON and Markdown; one-click copy of reproducible commands (with masked tokens and caveats).
- Artifact upload failures must be reflected as receipt `INCONCLUSIVE` or warnings according to required proof, never silently omit evidence.
- Ensure artifact TTL/retention, access checks and no public object bucket.

**Acceptance**
- Same stored run content produces byte-identical canonical receipt body/hash when excluding dynamic generated URL/timestamp fields.
- Tamper with artifact bytes or manifest field -> verification utility reports hash mismatch.
- Wrong workspace cannot read artifacts or receipts; signed URL expires as configured.
- Receipt clearly identifies `VERIFIED` vs `PARTIALLY_VERIFIED` vs `INCONCLUSIVE` and every required skipped browser.
- Browser-specific trace can be opened or downloaded; UI does not report unavailable data as passed.
- Reconnecting SSE client yields the complete event timeline and same final run result.

**Deliverables:** Professional evidence-first UI, receipt schema+validator, private artifact service.  
**Dependencies:** PRD-04.  
**Interview skills:** storage design, hashing, schema evolution, full-stack state management, UX, evidence integrity.

---

# PRD-06 — GitHub App, webhook automation and draft PR lifecycle (P1)

**Objective:** Complete the user workflow with safe, scoped GitHub integration. Never conflate agent suggested actions with authorized remote mutations.

**Stories**
- US-601: I install the GitHub App for explicitly selected repositories.
- US-602: A permitted issue triggers a job, and duplicated webhook deliveries do not create duplicates.
- US-603: After reviewing patch and evidence, I explicitly approve creating a draft PR.

**Work packages**
- GitHub App permission model: minimum required metadata/repo contents/PRs/issues; validate exact scopes against official endpoint docs. Avoid blanket installation-wide scope; installation selection and repo ID mapping enforced.
- OAuth state/CSRF protections, access token encryption or reference to secure secret storage; rotate/revoke appropriately.
- Validate raw-body GitHub webhook via HMAC-SHA256 with constant-time compare; dedupe delivery id/event action; enqueue asynchronously; rate limits/backoff.
- Branch naming deterministic but collision-resistant (`buildverify/<job-short-id>`); patch SHA and approval bound to same base SHA.
- Approval record includes actor ID, repo ID, exact patch hash, plan hash, requested operation and expiration; compare before every external write.
- Push via control plane only; create **draft PR** with summary, evidence receipt URL or text, test matrix and explicit limitations.
- Reconcile uncertain GitHub responses by searching existing branch/PR to avoid duplication; immutable remote operation ledger.
- If user lacks permission, show useful error rather than attempting privilege escalation.

**Acceptance**
- Same signed webhook delivered 3 times -> one logical job/action, deterministic tests.
- Invalid/missing signature or wrong repo installation -> rejected; no agent job created.
- Wrong user tries to create PR -> 403 and audit event.
- Plan/patch changes after approval -> approval invalid; requires new explicit authorization.
- Simulated timeout after GitHub created PR but before response -> retry returns existing remote PR, not duplicate.
- Draft PR never merges/updates protected branch or edits workflow files automatically.
- Works with stub GitHub server or isolated authorized test repository; real test must avoid touching unrelated repositories.

**Deliverables:** GitHub App integration, webhook tests, draft PR capability, audit trail.  
**Dependencies:** PRD-05.  
**Interview skills:** OAuth, HMAC, webhook processing, eventual consistency, idempotent external APIs, permissions.

---

# PRD-07 — Reliability, security hardening, deployment and observability (P1)

**Objective:** Show production engineering judgment with measurable instrumentation, failure drills and deployment automation.

**Stories**
- US-701: Maintainer sees queue lag, failure rates, token burn, browser test outcomes and traceable errors.
- US-702: A new developer starts locally with mock models and fixtures without paid keys.
- US-703: CI blocks tests/security regressions; deployment doesn't provide unsafe execution by default.

**Work packages**
- OpenTelemetry traces across HTTP, job dispatch, worker steps, runner API, GitHub calls and object storage; redact sensitive spans.
- Structured JSON logs, metrics (queue age, throughput, latency p50/p95, retries, crash recovery, token spend); optional Prometheus/Grafana dashboard.
- CI: Python typing/lint/unit/DB integration; TS lint/type/Vitest; Playwright demo tests; security scan; dependency audit; docker build and image pinning.
- Supply-chain control: pinned lockfiles, image digests, dependency change review, SBOM optional. Separate repo CI from executing untrusted user code.
- Deployment notes: control plane + worker + DB/Redis/MinIO in dev; isolate execution service on distinct host or real sandbox provider; mock-only public demo when isolation unavailable.
- Threat-model review, negative security tests, secret masking, user-role matrix, artifact TTL/delete tests, webhook replay tests, path/symlink traversal tests.
- Chaos tests: DB restart during dispatch, Redis restart, duplicated messages, dropped SSE, object-store unavailable, runner kill and orphan recovery.
- Document runbooks and backup/restore for metadata (not pretending backups are tested if not).

**Acceptance**
- CI runs from a clean checkout and deterministically passes with mock provider.
- `trace_id` traverses HTTP -> worker -> runner and links to artifact metadata for a fixture run.
- Load tests produce actual saved report with environment/concurrency/test command and p50/p95 (even if modest).
- All documented security-negative cases pass and runner is not exposed with root/shared secrets.
- Recovery from Redis outage demonstrated with controlled replay and DB integrity; no double PR.
- README has honest list of trusted/demo vs unsupported execution modes and known limitations.

**Deliverables:** Testable/deployable V1, observability screenshots/reports, hardened policy, runbooks.  
**Dependencies:** PRD-06.  
**Interview skills:** CI/CD, reliability, telemetry, security, deployments, performance testing.

---

# PRD-08 — Standout QA analytics: flakes, visual diffs, a11y and performance (P2)

**Objective:** Strengthen SDET/platform credibility through a suite of measurable, explainable quality tools.

**Features**
1. **Flaky-test analyzer:** Controlled reruns of an unchanged commit/browser; record pass/fail sequences, duration variance, intermittent error signatures and environment correlation. Compute simple `flake_observed = (passes>0 && failures>0)` over N runs; estimate rate and Wilson confidence interval; do not claim certainty from N=2. Suggest human-reviewed quarantine only.
2. **Failure clustering:** Normalize stack traces and error messages (remove volatile IDs/timestamps), group repeated root signatures by test ID/browser. Keep raw evidence.
3. **Visual regression:** Playwright screenshot snapshots, stable viewport/OS/font, approved baseline updates and diff images with review state.
4. **Accessibility:** `@axe-core/playwright`, report rules/tags/severity; treat automated checks as partial coverage, not full WCAG guarantee.
5. **Performance budget:** Lighthouse CI or browser performance capture; compare controlled baselines and flag regression with environment noise disclaimer.
6. **Prioritized test scheduling:** Safe test selection based on changed files and historical failures; **mandatory oracle tests are always included**. Record selection rationale and compare with full suite periodically.
7. **Optional privacy-first session-to-test reproduction:** Opt-in rrweb recording or sanitized HAR/trace upload. Mask passwords, inputs, cookies and tokens at capture; redact before persistent storage; transform events into a *reviewable* Playwright test proposal. Execute only approved generated tests on a controlled fixture, never the user's live session or real credentials.
8. **Optional mutation testing:** Run StrykerJS on a small JavaScript/TypeScript module under strict resource caps; calculate killed/survived mutants and expose test adequacy as advisory evidence. Mutation testing never modifies locked tests and never turns a failed application patch into `VERIFIED`.

**Acceptance**
- Seed one deterministic fail, one intentional flaky fixture, one browser-specific rendering diff and one axe violation; analyzer distinguishes each with reproducible steps.
- Flake detection reports observed sample size and false-positive/false-negative rates on synthetic fixture set.
- Changing a screenshot baseline requires explicit approval and stored provenance; not automatic healing.
- Performance comparison reports hardware variability and doesn't declare regressions from single noisy runs.
- Accessiblity report has evidence with browser/version, not just LLM-generated text.
- Scheduling optimization includes actual speed-up *and missed-failure analysis* relative to full suite.
- Stretch recorder case demonstrably masks sensitive fields and requires explicit consent; converted steps must be accepted by a human before entering the oracle suite.
- Stretch mutation case reports mutant count, survivors, test time and limitations; no security guarantee or blanket 'test quality proven' claim.

**Deliverables:** QA analytics screens, seeded experiments, comparative benchmark report.  
**Dependencies:** PRD-07.  
**Interview skills:** statistics, algorithms, metrics, test infrastructure, browser behavior, accessibility/performance engineering.

---

# PRD-09 — Full-stack app generation, adaptive context and A/B evaluation (P2)

**Objective:** Preserve the original Project #1's natural language → application capability, but under the same reliable workflows and QA gates.

**Features**
- Starter templates: a typed React/Next.js frontend + minimal REST backend; a predictable manifest describes languages, scripts, allowed commands and supported preview mode.
- Planner turns product requirement into small typed tasks; generator creates files via patch API in an isolated workspace.
- Optional WebContainers preview **only** for compatible in-browser Node.js projects, with clear support/failure handling; Python/backend apps preview through isolated runner only.
- Run scoped lint/type/unit/Playwright checks; package code with license and README explaining what works and what remains untested.
- Cost-aware context selection: incremental repo map, error-aware retrieval, low-cost model for classification, stronger model for patch when budget permits.
- Experiment arm A one-agent vs arm B 2-agent plan+review; fix same seeded tasks, track quality, tokens, attempts and wall-time.

**Acceptance**
- Given deterministic fixture requirements, platform can generate a small project in mock/golden mode reproducibly and export working files+tests.
- Real model generated apps are labelled experimental and graded by actual executable checks, not quality claims.
- No arbitrary language is claimed supported; unsupported request yields clear rejection.
- Editor cannot add scripts that override runner policy or exfiltrate host data.
- A/B report shows N, failure modes, cost, judge/test oracle, and limitation of model variance.

**Deliverables:** Original product concept preserved as safer, benchmarkable generation flow; context optimizer report.  
**Dependencies:** PRD-08 (or PRD-07 where independent).  
**Interview skills:** greenfield generation, model integration, code templates, context retrieval algorithms, experimental methods.

---

# PRD-10 — Optional cloud QA and platform research (P3; not required to publish)

**Objective:** Demonstrate architectural extensibility, without sacrificing core quality or claiming nonexistent capabilities.

**Choose at most one initially**

**Option A: BrowserStack/provider adapter**
- `BrowserProvider` interface with local Playwright and explicitly configured remote BrowserStack.
- Use only approved account and test project, with credentials stored in secret service.
- Test remote provider availability, matrix output and evidence normalization; label physical vs emulated devices accurately.
- Compare local and remote results by browser/OS/device versions, runtime/cost/coverage; account for network variance.

**Option B: Workflow engine comparison**
- Implement equivalent job subset in a Temporal proof-of-concept branch, benchmark crash recovery, developer complexity and maintenance against current Redis Streams/outbox.
- Write ADR recommending one option based on measured needs, do not operate duplicate production queues.

**Option C: Hardened sandbox provider**
- Add microVM or dedicated remote sandbox provider with attested image/version and least privilege. Perform red-team isolation tests; state known limits.

**Option D: Real load growth**
- Only if data justifies it, split workers and add queue backpressure/fairness or orchestration autoscale; measure before/after and document cost.

**Acceptance:** One proof-of-concept with testable adapter contract, evidence report, security/operational tradeoffs, and an ADR; all V1 tests remain green.

---

# Cross-phase implementation checklists

## Required each phase
- [ ] Actual repository audit/current-state status read.
- [ ] Scope and acceptance test agreed in issue/PR.
- [ ] No unauthorized external action or key leakage.
- [ ] API types/contracts updated if needed.
- [ ] Unit/integration/E2E/negative tests appropriate to feature.
- [ ] Changes reviewed for concurrency, user/tenant isolation and idempotency.
- [ ] Docs/migration updated, old behavior preserved or migration documented.
- [ ] `docs/IMPLEMENTATION_STATUS.md` updated with exact commands/results.
- [ ] Demo evidence collected only if actually observed.

## Release A Evidence MVP acceptance scenario
```text
GIVEN a deterministic deliberately broken app at base_sha and locked oracle test
WHEN I create a budget-capped job and approve its scoped plan
THEN a persistent worker reproduces the failure before editing
AND applies an allowlisted patch to a separate worktree
AND reruns the unchanged oracle and required regressions
AND tests Chromium/Firefox/WebKit with versioned evidence
AND a browser refresh/reconnection displays the same authoritative event history
AND killing a worker mid-task does not produce duplicate logical outputs.
```

## Release B portfolio-quality V1 acceptance scenario
```text
GIVEN the Release A working fixture and a selected user-authorized GitHub repository
WHEN the reviewer inspects the patch, receipt and browser matrix
AND explicitly approves a draft PR bound to that patch hash
THEN the platform safely pushes the approved branch and creates one draft PR
AND duplicate webhook/API retries never create a second PR
AND artifact and receipt access is workspace-authorized and tamper-detectable
AND CI/chaos/security tests pass on clean checkout.
```

## Report format for every phase
```markdown
## Completed: PRD-XX / task IDs
- Repository baseline: ...
- Implemented files/components: ...
- API/DB migration changes: ...
- Architecture decisions: ...
- Commands run + exact results: ...
- Security/negative tests: ...
- Known gaps and skipped tests: ...
- Measured metrics (or NOT MEASURED): ...
- Demo evidence / screenshots / trace refs: ...
- Next approved task: ...
```
