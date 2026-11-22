# Portfolio, product demo and engineering interview strategy

**Purpose:** Make the project prove broad engineering skill to employers without claiming competencies that aren't demonstrated. Implement the product first. This file explains what evidence to collect as you work.

## 1. Positioning for full-stack/SDE/backend/platform/SDET roles

**Core one-line pitch:** “I built an evidence-first autonomous software engineering platform that reproduces bugs on an immutable baseline, proposes changes in a constrained workspace, validates them against unchanged tests across browser engines, and creates audit-ready verification receipts and authorized draft pull requests.”

This is a *target narrative* until the features are implemented and tested. It is not an existing product claim.

**Credible breadth map:**

| Skill area | Real implementation to show | What this does NOT by itself prove |
|---|---|---|
| System design | Separation of control/worker/runner, event flows, ADRs | Production scale without load data |
| Backend/API | Typed FastAPI endpoints, auth, migrations, outbox, idempotency | Good API security unless negative tests exist |
| Frontend | Next.js dashboard, dynamic test matrix, SSE replay, accessible approval UX | Pixel-perfect design without UX evidence |
| Distributed systems | Redis Streams workers, leases, fencing, crash recovery | Exactly-once delivery or fault tolerance under all failures |
| Database | Postgres indexes, transactions, constraints, migrations | Optimized queries without EXPLAIN/benchmark |
| AI engineering | Structured plan/agent outputs, tool policy, budget limits, mock adapters | Model quality or superiority without eval |
| Security | Real isolation boundaries, least-privilege app, prompt injection denial | Guaranteed secure arbitrary execution |
| Testing | Locked oracle base/patch proof, Playwright three-engine matrix, traces | Real-device BrowserStack experience unless actually integrated |
| DevOps | CI, reproducible containers, deployment runbooks, metrics | Kubernetes expertise if not built/operated |
| Algorithms / DSA | Scheduling fairness algorithm, path context ranker, failure clustering with complexity discussion | Interview-level DSA proficiency without separate practice |
| Engineering communication | ADRs, benchmark methodology, clear limitations | Formal team experience unless actually earned |

**Explicit reminder:** This project is excellent portfolio evidence, but it does not replace DSA, language fundamentals, OS/networking/database knowledge, or timed coding practice for SDE interviews.

## 2. Signature demo A — Cross-browser bug to verified patch

**Setup:** Synthetic checkout app containing a known reproducible browser-specific bug. Locked oracle test stored outside editable source. Pinned runner versions.

**Steps on screen:**
1. Show issue and exact base commit; select browser matrix and cost cap.
2. Display structured plan and approval; show allowed paths.
3. Show baseline failing test with a trace (prove bug existed).
4. Show proposed diff and reviewer check; visibly inspect real changed code.
5. Show patch re-test using the *same* oracle hash and regression matrix.
6. Display receipt with environment fingerprint, tested vs skipped, trace links, commit/diff hashes.
7. Optionally approve draft PR in an isolated authorized demo repo and open the PR.

**Interview question:** Why is a Playwright test becoming green insufficient to prove the app was fixed?  
**Answer to substantiate:** Testing system may have changed assertions, mocked the failure, changed environment or merely rerun a flake. Preserve the oracle, reproduce baseline, compare same environment/test and show regression evidence.

## 3. Signature demo B — Durable recovery under worker death

**Setup:** Controlled fault injection into worker between DB commit and Redis acknowledgement.

**Steps on screen:**
1. Queue a job and show active lease and consumer.
2. Trigger documented crash injection.
3. Restart/replace worker; observe stale claim and new attempt ID.
4. Show persisted step/outbox, no duplicate logical result/PR, event timeline preserved.
5. Present automated integration test and DB constraint that prevent duplicates.

**Questions:** Why is Redis Streams not exactly-once? What if old worker wakes up? What if GitHub succeeds but the HTTP response is lost?  
**Evidence:** at-least-once delivery with idempotency, fencing tokens, CAS and remote side-effect reconciliation.

## 4. Signature demo C — Agent security and bounded authority

**Setup:** Deliberately malicious synthetic GitHub issue asking for unauthorized files/commands.

**Steps on screen:**
1. Show issue text with prompt-injection attempt.
2. Model proposes tool call; policy engine denies based on signed actor/scope, not based on agent response.
3. Show audit log and no unauthorized shell/network/GitHub operation.
4. Show resource quota and isolated runner boundary; run disposable security tests only on dedicated host.

**Questions:** Why can't a system prompt alone enforce security? What's the difference between a browser WebContainer and a real sandbox?  
**Evidence:** explicit server authorization with negative tests; separate runner and no secrets inside workload.

## 5. Signature demo D — Quality analytics with meaningful numbers (P2)

- Show a fixture flaky test passing/failing on unchanged source; provide number of reruns and rates.
- Compare failure clustering with manually labeled root causes.
- Show screenshot visual diff approval, axe report and a mutation-testing example.
- Describe where automation cannot make strong guarantees and why human review remains necessary.

## 6. Signature demo E — System performance and experimental comparison

- Compare 1 worker versus N workers, equal CPU resources or explicitly document disparity.
- Compare one-agent fix versus bounded planner/reviewer approach on identical fixture set.
- Report median and p95 queue latency, completion rate, validated repairs, model costs, repeat count and machine specs.
- Demonstrate a simple flamegraph/trace revealing a bottleneck; explain an optimization made based on evidence.

**Rule:** A '50% performance improvement' is never a resume bullet without a reproducible benchmark demonstrating what changed and the exact denominator.

## 7. Suggested README structure for your actual GitHub repository

1. One sentence: problem solved, scope and the working demo.
2. Animated gif/video of real end-to-end run (redact secrets).
3. Architecture diagram; trust boundaries and why they exist.
4. Feature checklist clearly labelled **Implemented / Experimental / Planned**.
5. Quickstart with zero paid API keys (mock mode), demo fixture and test command.
6. Supported browser engines and specific versions; hardware/OS requirements.
7. Runtime and security model with limitations.
8. Actual measurements with N and reproducible benchmark commands.
9. GitHub App permissions/approval mechanism and privacy statement.
10. ADR links and open issues; third-party acknowledgments.

## 8. Candidate interview questions to practice

1. Why didn't you use Redis Pub/Sub for durable jobs? What guarantees do Redis Streams and Postgres provide?
2. Explain the transactional outbox and a case in which duplicate processing still occurs.
3. How does a fencing token stop a zombie worker writing stale state?
4. How are GitHub writes kept idempotent when HTTP responses are lost?
5. What prevents a malicious repository README from redefining agent tools?
6. Why is running generated code in Docker on your developer laptop not an adequate trust boundary?
7. How do you prove a repair without letting the agent modify its own acceptance criteria?
8. What are differences among Chromium, Firefox and WebKit? Why aren't they equal to physical devices?
9. How do you handle SSE event sequence gaps, disconnects and duplicate deliveries?
10. How would you choose schema indexes and avoid expensive queries as event logs grow?
11. Which metrics indicate retries are harming rather than helping performance?
12. Would you migrate to Temporal? Under which concrete complexity threshold?
13. How do you compare flake rates with small samples and avoid false positives?
14. What's the complexity of the scheduler and how do you avoid starvation?
15. What do you personally understand and own vs what was composed from open-source dependencies or produced by an AI assistant?

## 9. Milestone rubric before adding resume bullets

| Level | Evidence available | Reasonable description |
|---|---|---|
| Concept | Mockups and PRD only | “Designed a proposed...” not “Built” |
| Working prototype | Repeatable happy path, some tests | “Prototyped...” with limitations |
| Strong software project | Durable errors, real QA, isolated execution, tests/CI, receipts, docs | “Engineered / implemented...” with exact scope |
| Measured engineering showcase | Crash drills, security tests, baseline-vs-patch proof and benchmark data | Add verified numbers to resume |
| Operational platform | Public deployment with proper isolation, monitoring, uptime history | Only then describe operational scale and reliability |

## 10. Portfolio release checklist

- [ ] Replace all 'planned' language with verified implementation status.
- [ ] Remove any secrets and real user data from video, screenshots, logs and benchmark inputs.
- [ ] Re-run clean clone setup and CI with deterministic mock model.
- [ ] Link to real recorded demo artifacts, receipt verifier and reproducible sample case.
- [ ] Cross-check claims against actual source and test evidence, include limitations.
- [ ] Be prepared to independently explain each major subsystem rather than attributing all design to Codex/Claude.
