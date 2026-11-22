# Testing, security, benchmarking and hiring evidence

**Applies to every PRD phase.** Design purpose: a coding agent cannot independently declare itself correct or secure. The platform must emit evidence that humans and deterministic checks can inspect. The sample repositories must contain synthetic data only.

## 1. Threat model

### Assets worth protecting
- GitHub organization/repo access and installation tokens; LLM provider keys; application DB and artifacts.
- Developer's local files/host OS/cloud metadata; other tenants' repositories and receipts.
- Integrity of oracle acceptance tests, branch contents, CI workflow files, PR approvals and audit logs.
- User budget, resource quota, network quota and platform availability.

### Adversaries and untrusted inputs
- Malicious repository owner, compromised public dependency, malicious PR/issue text, untrusted model output, compromised agent plugin/tool, malicious run logs, overprivileged GitHub installation, cross-tenant user.
- Prompt injection delivered by README/comments/error output; deceptive test result; malicious symlinks; package manager lifecycle scripts; path traversal; fork PR with untrusted workflow.

### Trust boundaries
1. User request to API → validated identity + workspace authorization.
2. Public Github webhook → HMAC signature and replay/dedup verification.
3. Issue/repository content → treated as **data**, never trusted instructions.
4. LLM recommendation → validated typed tool call subject to server policy.
5. Model/agent to execution runner → isolated gateway with ephemeral identity and restricted test command allowlist.
6. Runner to object storage → upload-only scoped credentials, quarantine stage and integrity digest.
7. Control plane to GitHub → only after human approval bound to exact repo, plan and patch hashes.
8. Authenticated user to artifact read → workspace check + short-lived signed access.

## 2. Security control matrix

| Risk | Required control | Negative test / evidence |
|---|---|---|
| Prompt injection from issue/README | Separate system policy and data; allowlisted tools and per-action authorization enforced outside LLM | Issue asks agent to read secrets, open URL, change workflow; action denied, policy event present |
| Path traversal / symlink escape | Resolve and verify canonical path under worktree on every read/write; avoid TOCTOU via secure filesystem APIs; deny symlink escapes | Patch targets `../../.env`, symlink points outside; blocked |
| Secret exfiltration | Never mount secrets; block egress; redaction, static secret scanner | Test process attempts metadata endpoint and API host; traffic blocked; no secret leak |
| Container escape / host access | Dedicated isolated worker host; non-root, no Docker socket, no privileged mode, dropped caps, seccomp, read-only root and quotas; microVM preferred for stronger isolation | Disposable security fixture attempts prohibited mounts/process behavior; alert/block; document platform limitations |
| Dependency install attacks | Pin lockfiles; trusted package cache/approved registry; review install scripts; separate restricted stage | Dependency scripts attempt curl/host access; denied or install aborted |
| Cross-tenant data leak | Authorize every job/artifact/repository by workspace; distinguish 404/403 without leaking | User B requests job/receipt/artifact owned by A; blocked |
| Github webhook forgery | HMAC SHA-256 over raw payload, timing-safe compare, delivery-ID de-dup, installation scope match | Invalid/missing signature; replay; wrong installation; no job created |
| Unauthorized PR write | Explicit approval with plan SHA, patch SHA, repo ID, base SHA; minimal GitHub App permissions | Change patch after approval, or wrong role, then call create; rejected |
| Duplicate worker/PR effects | Transactional DB outbox, leases/fencing, stable idempotency key, reconcile external side effects | Kill after DB commit and after remote API commit; one logical result/PR |
| Budget exhaustion | Hard token/cost/runtime/attempt caps outside model | Model requests extra calls after cap; hard stop with recorded reason |
| Log and artifact leakage | Secret redaction; private bucket; short-lived authenticated downloads; storage TTL | Expired URL fails; redacted tokens not in logs/receipt |
| CI workflow injection | Never auto-edit `.github/workflows/**`; treat remote PRs as untrusted; workflow approval required | Agent tries to alter deploy workflow; denied |
| Browser auth bleed | New contexts without user's cookies; isolated state per run; restricted internal test URL | Test cannot see another fixture/session's data |
| Remote provider outage | Circuit breaker / bounded retry / explicit `INCONCLUSIVE` | Provider 5xx leads to non-success report |

**Disclosure:** Docker is a useful isolation layer but not a security proof. For untrusted public code, hardened remote sandbox/microVM and external security review may be necessary. Do not expose unrestricted code execution on a public endpoint before such a review.

Primary references: https://docs.docker.com/engine/security/ ; https://docs.docker.com/engine/security/rootless/ ; https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html ; https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries ; https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app .

## 3. Trustworthy automated verification

**Oracle integrity:** Use externally controlled, independent oracle tests. Freeze test hash before patch. Patch author/agent must not edit these tests or test runner config. Separate `PATCH_EDITABLE_PATHS` from `ORACLE_TEST_PATHS`. Store baseline and patch test run manifest referencing same oracle digest.

**Classification hierarchy:**
1. If runner failed to boot/dependency mismatch: `INFRA_ERROR`, never `PRODUCT_FAIL`.
2. If reproducible test assertion fails at same commit: `PRODUCT_OR_TEST_FAIL` pending evidence.
3. If failure changes outcome over controlled reruns of unchanged commit: `FLAKY_SUSPECT` (sample size required).
4. If app code changed and oracle turns green on patched commit, regression mandatory tests green: `VERIFIED` only when all other gates hold.
5. If test itself changed, mark `TEST_CHANGED`, block automatic verified status.
6. If patch contains illegal scope or needed approval absent: `POLICY_BLOCKED`.

**Never rely on LLM interpretation alone** for pass/fail or reason code; reviewer narrative is commentary.

## 4. Test pyramid and fixtures

### Unit tests
- State transition validator (valid and invalid transitions), CAS/version conflict, idempotency hash.
- Budget arithmetic, currency decimal accounting, token limit off-by-one.
- Plan JSON schema, file allowlist/path normalization, receipt canonicalization/hashes.
- Failure signature normalization, flaky observation interval, test prioritization model.
- Scheduler and heartbeat lease expiration with fake clock, not fragile sleep.

### Integration tests
- Postgres migrations from blank database and version upgrades; rollback documented.
- Redis Streams produce/claim/ack/redelivery, retry and dead-letter with real local test container.
- DB outbox publisher restart mid-batch and event sequence monotonicity.
- Auth roles and workspace query/endpoint/artifact read isolation.
- MinIO upload/access/expiry/tamper check; GitHub App mocked HTTP signed webhook and response timeout.

### Browser E2E
- Browser matrix across Chromium, Firefox, WebKit on a pinned OS/browser package environment.
- Seed per-test data; stable viewport/time/timezone/locale; deterministic test IDs.
- Trace/screenshots on failure; JUnit/JSON report; file paths + hashes in receipt.
- Demo app: checkout flow, auth/session route, responsive page, one browser-specific CSS bug.

### Chaos tests
- Kill worker before task execution, during task execution, after DB commit before ACK, during artifact upload and during PR creation response.
- Stale worker with expired lease attempts to commit after new owner; should be rejected.
- Redis restart + outbox re-publish; DB restart + worker retry; lose SSE connection then replay.
- Runner hangs indefinitely; enforce wall clock and cleanup; cancel mid-browser-test.

### Security tests
- Prompt injection fixture in issue body, README and test stdout.
- Symlink traversal, `..`, percent-encoding path confusion, illegal write attempts.
- Untrusted test process seeks `/proc`, host env, metadata IP, unauthorized DNS/HTTP.
- Auth bypass, RBAC mismatches, cross-workspace UUID guesses, signed URL expiry.
- Invalid GitHub signature, missing state/CSRF, duplicate webhook, unauthorized PR attempts.

## 5. Controlled evaluation fixture set

Create five or more **owned/licensed**, small fixture repositories with clear licenses and independent oracle tests:

| Fixture | Intent | Baseline | Valid patch expectation | Important failure |
|---|---|---|---|---|
| FX-01 Cart totals | Pure function + UI bug | Incorrect discount/rounding or NaN | Correct calculation, all required tests | Cannot edit oracle to pass |
| FX-02 Browser-specific CSS | WebKit/Firefox difference | One engine fails layout/interaction | All engine checks pass | Detect browser-specific failure honestly |
| FX-03 Async race | Concurrency/race | Deterministic timing-controlled failure | Correct synchronization and repeatable green | Not rely on one lucky rerun |
| FX-04 Auth leak | Access control | Unauthorized route exposure | 403/404 as appropriate | Test never exposes sensitive fixture token |
| FX-05 Flaky click | Intentional nondeterminism | Inconsistent pass/fail | Classify as flaky; do not apply arbitrary app fix | False claim of patch success |
| FX-06 Infra failure | Environment fault | Missing package / runner timeout | Inconclusive/retry, not app patch | Wrong error category |
| FX-07 Prompt injection | Malicious issue/repo text | Requests unauthorized tool | Policy denial | Model shouldn't bypass tool controls |
| FX-08 Worker duplication | Queue failure | Multiple deliveries | One committed logical effect | Repeated PR creation |

Store fixture seed, base SHA, locked oracle SHA, scripts, tool versions and expected classification in a manifest. Use licensed or personally written fixtures. Protect oracle tests from model context leaks when measuring agent generalization, where practical. Keep separate training/dev and holdout cases.

## 6. Benchmark protocol (no invented results)

### Evaluation questions
- **Repair validity:** Fraction of fixtures whose baseline reproduces and patched code passes same oracle and required regressions.
- **Cost efficiency:** Money/tokens per verified repair; retries and rejected patches included.
- **Operational reliability:** Terminal completion count, queued/running job loss, duplicate side effects under faults.
- **QA accuracy:** Flake-vs-product classification precision/recall over labeled cases; browser-specific fault recognition.
- **Speed:** p50/p95 job duration, queue time, runner startup, browser suite wall time under stated concurrency.
- **Context efficacy:** Full-context vs repo-map file identification and patch success.

### Core formulas
```text
reproduction_rate = reproducible_baselines / attempted_issues
validated_repair_rate = verified_repairs / attempted_issues
conditional_repair_rate = verified_repairs / reproducible_baselines
false_verification_rate = falsely_marked_verified / jobs_marked_verified
cost_per_verified_repair = total_model_and_compute_cost / max(verified_repairs, 1)
recovery_rate = successfully_completed_fault_runs / all_fault_runs
duplicate_external_side_effects = count(PR duplicates or repeated forbidden writes)
flake_observed = (passes > 0 AND failures > 0) on identical code/environment
```

A score on 4 cases is not a claim of general ability. Always report `N`, random seed or controlled setup, model version, repo/test identity, environment, number of reruns and confidence/uncertainty where useful.

### Methods
1. Pre-register fixture list, success definitions and test oracle before tuning.
2. Version-control config: base SHA, model name/revision, temperature if supported, allowed tools, budgets, runner image digest and browser versions.
3. Repeat stochastic model runs where budget permits. Use deterministic mock in CI and separate paid live benchmark.
4. Run A/B with the same suite; disclose changed variables; record all failures/timeouts as outcomes.
5. Do not use LLM judging as the sole quality ground truth. Prefer tests and human review of code semantics/security.
6. For each benchmark, save manifest, raw JSON/CSV result, aggregation script, plots and narrative showing limitations.
7. Never use private test solutions in prompts to the agent. If using public SWE-bench instances, disclose potential benchmark contamination and computational limitations.

### SWE-bench optional evaluation
SWE-bench Verified contains 500 expert-verified issue instances (https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/datasets.md). It may require substantial dependencies/compute and may not match a frontend browser QA product. Use tiny declared subsets strictly for supplementary comparisons; do not imply full benchmark results or leaderboard standings.

### Load benchmark setup
- Use k6 (https://grafana.com/docs/k6/latest/ ) to create/retrieve jobs with a deterministic mock worker; separately test browser workers.
- Vary concurrent users/jobs with **fixed** machine specs, DB pool size, Redis version, runner limits.
- Log actual p50/p95 and error rates; measure queue backpressure and memory.
- When comparing sequential vs sharded tests, ensure equal resource budget; show resource tradeoff, not speed alone.
- Publish a baseline report template:

```markdown
# Benchmark report — [run id]
Date / commit / environment / specs:
Workload / fixture cases / N / seed:
Model provider + version and token price assumptions:
Run limits / concurrency / resource quotas:
Success criteria / required browser versions:
Raw result paths:
Throughput and p50/p95 latency:
Validated repairs / baseline reproduction / false verifications:
Costs (model and infrastructure calculated separately):
Worker failures / recoveries / duplicate side effects:
Security failures / incomplete or skipped tests:
Limitations and future work:
```

## 7. Accessibility, visual regression and frontend quality tests

- WCAG-oriented automated checks: `@axe-core/playwright` documented integration: https://playwright.dev/docs/accessibility-testing . Automated scans cannot guarantee full accessibility compliance; complement with keyboard and screen-reader spot checks.
- Visual regression: stable screenshot environment, per-browser reference images, explicit human approval for snapshot updates: https://playwright.dev/docs/test-snapshots .
- Performance: Lighthouse CI (https://github.com/GoogleChrome/lighthouse-ci), consistent hardware/network emulation and repeated samples. Avoid unrealistic single-run assertions.
- Dashboard: readable error details, focus management for approval dialogs, accessible status labels beyond color, progress updates announced appropriately, log virtualization and network loss UI.

## 8. Data protection, compliance and supply chain

- Do not persist raw full prompts/private code unnecessarily; avoid logging secrets; configure retention and delete actions.
- Use test/demo GitHub installation on only a selected repo; production data flow disclosures and user consent for LLM provider required.
- Pin runtime/tool versions, audit dependencies, produce SBOM if relevant; review changes to lockfiles and scripts.
- Consider SAST with Semgrep and image/dependency scan with Trivy, but remember findings are not proof of vulnerability absence.
- Document public/private repository data processing, source license and whether uploaded artifacts contain code.
- Consider third-party model provider privacy and geographic/compliance requirements before claiming enterprise readiness.

## 9. Interview / resume engineering evidence checklist

For each demonstrated feature record: **file or PR implementing it**, **test that validates it**, **screenshot/log/trace showing it**, **actual metric** and **design tradeoff you can explain**.

| Target capability | Proof artifact to collect | Interview question to rehearse |
|---|---|---|
| Distributed systems | Worker crash replay integration test, lease diagram, idempotency table | Why Redis Streams and DB outbox? Where can duplicates still occur? |
| Backend engineering | FastAPI contracts, migrations, RBAC tests, query plans | How do auth + tenant-scoped queries prevent data exposure? |
| Frontend | Accessible run dashboard, trace viewer, reconnect test | How do you handle out-of-order events and slow logs? |
| Security | Threat model, prompt-injection and isolation negative tests | Why is Docker/AST scanning alone insufficient? |
| QA/SDET | Same oracle baseline-vs-patch proof, 3-engine matrix, trace | How do you distinguish a product bug from a flaky test? |
| CI/CD | Passing PR checks, reproducible mock mode, release image digest | How would you deploy safely without running unknown code on control plane? |
| AI application | Typed tool outputs, budget ledger, mock vs real eval | Why use multiple agents at all? How do you measure added value? |
| Algorithms | Fair scheduler, context ranker, failure signature grouping | Complexity and starvation/false-merge tradeoffs? |
| Databases | Postgres schema, indexes, transaction+outbox tests | How do you avoid partial updates or double writes? |
| Product/design | Verification Receipt and reviewer flow | What valuable problem is solved vs OpenHands/SWE-agent/Playwright? |

**Portfolio publish rule:** Prefer 4 genuinely working, measured pillars (durable orchestration, sandboxed execution, browser QA, evidence-backed PR) over 15 features with attractive mock dashboards.
