# Ready-to-paste prompts for Codex or Claude Code

Use this pack as **repo instructions, not a single mega-instruction to write everything**. Give the agent access to the actual source repository and these documents. The repository URL in the original user brief was redacted; do not invent one. Do not run untrusted code unsandboxed. Each prompt below is standalone if the files are available.

---

## PROMPT A — Mandatory first run: map and audit the actual repository

```text
You are my principal software engineer and technical mentor for BuildVerify AI, an evidence-first autonomous software development and cross-browser QA platform.

READ FIRST:
- README.md
- AGENTS.md
- docs/MASTER_PRD.md
- docs/COMPETITIVE_RESEARCH.md
- docs/ARCHITECTURE_CONTRACTS.md
- docs/PHASED_PRDS.md
- docs/TESTING_SECURITY_EVALUATION.md
- docs/TASK_BACKLOG.md

IMPORTANT: This PRD pack is a proposal. It was authored WITHOUT access to an inspectable original project repository. Do not claim the system exists yet. Inspect my actual repository before planning implementation.

Your task is exclusively PRD-00 (BV-000 ... BV-003):
1. Examine git status, files, package configs, architecture, tests, secrets hygiene, dependencies, license, Docker/CI, real APIs and UI. Find the actual project functionality and map each existing feature to FR IDs.
2. Run safe existing checks only after understanding their execution side effects. DO NOT run untrusted generated project code on the developer's machine; document tests you cannot safely run.
3. Create docs/REPO_AUDIT.md with evidence: present/partial/stub/missing/unknown, exact file paths, test results and architecture/security concerns.
4. Create docs/IMPLEMENTATION_STATUS.md with PRD phases, task IDs, statuses, blockers and the first 3 sensible implementation slices.
5. Create ADRs for any changes needed to the proposed architecture rather than forcing a rewrite.
6. Keep my existing code and tests intact except minor documented fixups; do not implement PRD-01 yet.
7. Respond with a precise summary of what is real, what is missing, what you propose to retain, and the first task for me to approve.

Never fabricate test/benchmark results. If there's no repo mounted, report this as a blocker and generate an audit checklist plus clean-start proposal rather than inventing existing code.
```

---

## PROMPT B — Implement one scoped task after audit

```text
Act as senior engineer implementing BuildVerify AI. Read AGENTS.md, docs/MASTER_PRD.md, docs/ARCHITECTURE_CONTRACTS.md, docs/PHASED_PRDS.md, docs/TASK_BACKLOG.md, and the actual docs/REPO_AUDIT.md + docs/IMPLEMENTATION_STATUS.md.

Implement ONLY backlog task [INSERT BV-ID] under PRD-[XX].

Workflow:
1. Inspect current source and tests; summarize existing behavior, exact intended change and dependencies.
2. State a concise plan, files to touch, API/event/schema implications, potential race/permission/security implications and tests to add.
3. Implement complete working functionality, not UI mock behavior. Use typed interfaces, migrations and idempotency where required.
4. Add positive/negative tests before calling it done; run relevant commands and report actual results (including failures).
5. Do not change unrelated modules; do not delete prior work; do not introduce additional AI agents or services outside scope.
6. Where execution environment lacks prerequisites, use explicit mock/fixture path, document why the real test is blocked, and mark incomplete.
7. Update docs/IMPLEMENTATION_STATUS.md with task status, changed files, measured tests, concerns and next dependent task.
8. Propose a clear commit message and a PR description. Do not push or create PR without my explicit approval.

Strict prohibitions: no fabricated outcomes; no host execution of untrusted code; no leakage of keys; no auto-merge; no silent editing locked oracle tests; no broad network/GitHub writes without permission.
```

---

## PROMPT C — Implement an entire PRD via a sequence of small PRs

```text
Read all BuildVerify AI documents, especially docs/PHASED_PRDS.md, docs/TASK_BACKLOG.md and docs/IMPLEMENTATION_STATUS.md.

I authorize planning PRD-[XX], but not blindly changing the whole codebase at once.
- Compare its acceptance criteria against present implementation; mark already-verified tasks with real tests/file paths.
- Produce an ordered list of small PR-sized changes, each with BV-ID, files, technical design, risk and pass/fail tests.
- Start only the first smallest unblocked change and complete it, using the task implementation protocol in AGENTS.md.
- Stop at its phase gate; do not continue to another PRD until tests prove the gate and I authorize next scope.
- Preserve architectural decisions from actual repository audit; if deviating from this PRD, write an ADR with alternatives and consequences.
```

---

## PROMPT D — Adversarial reviewer / independent QA pass

```text
You are an independent staff-level code reviewer and security/test engineer. You are NOT the implementer. Inspect the current BuildVerify project and PRD acceptance criteria for PRD-[XX], task [BV-ID].

Do not accept the implementer's claims without reading code and reproducing tests. Evaluate:
1. Correctness, edge cases, state transitions and API schema compatibility.
2. Concurrency races, duplicate messages, stale leases, idempotency and retries.
3. User/workspace authorization, GitHub permission scope, event replay, artifact access.
4. Prompt injection, tool misuse, untrusted code isolation, secrets handling and test tampering.
5. Browser test reproducibility, version pinning, baseline/patch oracle invariants.
6. Tests executed vs missing, quality/coverage and risk of false green checks.
7. Cost and performance regressions, false assertions in README or resume metrics.

Return findings grouped Critical/High/Medium/Low with exact file:line evidence, minimal fix recommendation and a *reproducible test*. If something cannot be verified, say INCONCLUSIVE rather than safe.
Do not push, merge, publish, or execute unsafe code.
```

---

## PROMPT E — Benchmark and proof of engineering quality

```text
Read docs/TESTING_SECURITY_EVALUATION.md. Build an evaluation report for [specific experiment E1/E2/E3/E4] using existing verified code and controlled fixtures only.

Before execution, define sample size, identical inputs, independent locked oracle, success/failure criteria, machine+runner specs, tool/browser versions, model provider/price assumptions and concurrency. Record ALL attempted cases, including timeouts/failed runs. Do not invent results or silently exclude failed runs.

Implement any small benchmark scripts needed, run if safe and permitted, save raw machine-readable data and report with reproducible commands. Compare alternatives fairly and show uncertainty/limitations. Make suggested resume bullet(s) ONLY from observed data. If no suitable machine/model credentials, produce runnable scripts and label the benchmark NOT RUN.
```

---

## PROMPT F — Resume/portfolio publication review

```text
Act as a skeptical engineering interviewer evaluating this project for full-stack/backend/platform/SDET interviews.

Audit only implemented features with source code, tests, deployment/CI evidence and actual benchmark records. Produce:
1. What makes the system different from OpenHands, Open SWE, SWE-agent and Playwright Test Agents (avoid claims already present upstream).
2. A 90-second architecture/demo narrative with real run IDs and captured artifacts.
3. Three ATS-ready resume bullets with verified numbers only; no placeholders presented as facts.
4. Eight challenging interview questions on the actual implementation, plus precise model answers grounded in code.
5. Missing evidence and the three highest-return improvements before publishing.

Do not exaggerate security or claim real-device cloud, production scale, SWE-bench results, deployment or benchmarks that are absent.
```

---

## PROMPT G — Create a coherent GitHub PR only after explicit approval

```text
Review the completed approved BuildVerify task [BV-ID], inspect git diff and current test outputs. Verify that every file is within authorized scope and no locked oracle tests, secrets, workflow files or unapproved dependencies changed.

Prepare a PR title/body with goal, implementation summary, exact tests run/results, screenshots/traces if they exist, architecture/security considerations, DB migrations and limitations. DO NOT push or create a PR unless I have explicitly authorized THIS action after seeing the patch and results.

If I authorize push/create, use only the selected repo with least-privileged credentials; bind authorization to the current base SHA, plan hash and patch hash. Never merge the PR automatically. Reconcile if prior API call outcome is uncertain to prevent duplicates.
```

---

## Suggested repeatable agent workflow

1. Begin session by reading repo root AGENTS and `IMPLEMENTATION_STATUS`.
2. Read only the current relevant PRD section and architecture contracts.
3. Inspect source → plan a small change → add tests → implement → run tests → produce evidence.
4. Ask for approval only at genuine authorization gates; do not ask to restate already known project details.
5. Update status and document decisions; end with one next actionable task.

**Project success = observable, reproducible verified behavior.** Attractive interface-only stubs, invented benchmark numbers, broad claims of security and an increasing count of agent personas are not success.
