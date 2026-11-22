# BuildVerify AI product plan

Start with a local verifier that runs the same independently maintained browser test against two Git commits. A patch may come from any author. The dashboard, GitHub integration, and AI suggestions build on the verifier.

This plan and the numbered PRDs define the active build sequence. The [original PRD pack](reference/buildverify_prd_pack/README.md) is retained for background and design details.

## Shared implementation decisions

- **First user and target.** A developer or small team maintaining an approved Git repository. The first supported application profile is a React/TypeScript Vite app with npm, a committed lockfile, and independently maintained Playwright tests. Start with an owned checkout fixture, then run the same workflow on a second developer-owned repository.
- **Stack.** Python CLI and verification library, a pinned Playwright Linux runner image, FastAPI and Pydantic for the later API, PostgreSQL with Alembic for durable state, and a Next.js/TypeScript dashboard. Use one PostgreSQL-backed queue and SSE for live events. PostgreSQL supports `SKIP LOCKED` for queue-like consumers. [PostgreSQL SELECT documentation](https://www.postgresql.org/docs/current/sql-select.html)
- **Runner boundary.** Register repos and profiles explicitly. Resolve refs to immutable commit SHAs and export clean trees from Git. Give the app process separate disposable storage from the test harness. The app and harness communicate over loopback in an isolated network namespace. Keep the profile, tests, reporter, and result directory outside the app’s writable filesystem. Use a prewarmed dependency cache and block network access during testing. Give the workload resource limits, a deadline, and no runner credentials. The product is deployable on a developer-owned machine or VM for approved workloads. [Playwright Docker documentation](https://playwright.dev/docs/docker)
- **Verdict contract.** Keep execution state separate from verification verdict. Use `VERIFIED` when the expected baseline assertion reproduces, the same test passes on the candidate, and every required regression check passes. Use `FAILED` for a repeatable candidate assertion failure or new regression under comparable conditions. Use `INCONCLUSIVE` for missing required evidence, an unreproduced baseline, mixed outcomes, or a changed test environment. Use `POLICY_BLOCKED` for work outside the approved profile. Store case-level reasons and attempts even when there is no verdict.
- **Handoff format.** Give each numbered PRD its own Markdown file under `docs/prds/` when writing the pack to disk. Keep the shared decisions above in `docs/PRODUCT_PLAN.md`, link them from every PRD, and track exact commands, results, and open prerequisites in `docs/IMPLEMENTATION_STATUS.md`. Keep the archived `AGENTS.md` with the original reference files when extracting the pack.

## Roadmap

| PRD | Depends on |
| --- | --- |
| [PRD-01 — Run the first real verification](prds/PRD-01-verification-cli.md) | Nothing. This is the greenfield starting point. |
| [PRD-02 — Ship the browser matrix and Verification Receipt](prds/PRD-02-receipt-and-replay.md) | PRD-01. |
| [PRD-03 — Add the dashboard and durable run execution](prds/PRD-03-dashboard-and-durable-runs.md) | PRD-02. |
| [PRD-04 — Pilot with GitHub pull requests](prds/PRD-04-github-pilot.md) | PRD-03. |
| [PRD-05 — Suggest a bounded AI repair](prds/PRD-05-ai-repair-suggestions.md) | PRD-04. |
| [PRD-06 — Explain flakes and recurring failures](prds/PRD-06-flake-and-failure-analysis.md) | PRD-04. Can be built independently of PRD-05. |
| [PRD-07 — Review visual and accessibility changes](prds/PRD-07-visual-accessibility-review.md) | PRD-04. |
| [PRD-08 — Generate and validate an app starter](prds/PRD-08-verified-app-starter.md) | PRD-05. Optional extension that keeps the original prompt-to-app concept. |

## Prior product research

| Reference | What it already does | BuildVerify’s product decision |
|---|---|---|
| GitHub Copilot and OpenHands | Copilot can work on repository changes and open PRs. OpenHands offers a modular agent SDK. | Make verification available to any patch author. Add a narrowly scoped AI suggestion workflow after the verifier ships. [GitHub Copilot cloud agent](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/use-cloud-agent-on-github) · [OpenHands SDK](https://github.com/OpenHands/software-agent-sdk) |
| Playwright | Runs Chromium, Firefox, and WebKit, captures inspectable traces, and offers agents that can generate and heal tests. | Reuse Playwright and give the reviewer a side-by-side comparison using the same locked test. A patch that changes the acceptance criteria requires a new verification run with independently approved criteria. [Browsers](https://playwright.dev/docs/browsers) · [Trace Viewer](https://playwright.dev/docs/trace-viewer) · [Test agents](https://playwright.dev/docs/test-agents) |
| Chromatic and Currents | Chromatic tracks approved visual baselines. Currents surfaces flaky tests. | Add visual review and controlled flake replay as separate workflows. Show which commit, environment, and attempts explain the finding. [Chromatic baselines](https://www.chromatic.com/docs/branching-and-baselines/) · [Currents flaky tests](https://docs.currents.dev/dashboard/tests/flaky-tests) |
| BrowserStack and GitHub Checks | BrowserStack provides hosted browser and device testing. GitHub Checks publishes results against a commit SHA. | Run three local browser engines and publish a check for the exact tested PR commit. Give reviewers a clear stale-evidence state when a PR moves ahead. [BrowserStack Automate](https://www.browserstack.com/docs/automate/playwright/overview) · [GitHub Checks API](https://docs.github.com/en/rest/checks/runs) |

The differentiators to build and demonstrate are **a replayable Verification Receipt, an explanation when two runs can’t be compared, and a GitHub check tied to the exact tested commit**. Visual reviews and AI suggestions become more useful once those foundations are in place.

## Handoff

Give Codex the shared implementation decisions, **one numbered PRD**, and the current implementation status. Replace `PRD-01` with the next number only when its dependencies have passed.

> Implement only PRD-01. Inspect the current workspace and follow the shared BuildVerify decisions. Work through this PRD’s numbered steps in order, run the exit-gate checks, and record commands, actual results, and any blocked checks in `docs/IMPLEMENTATION_STATUS.md`. Stop at this PRD’s exit gate and report which criteria passed.

For the first portfolio demo, use **one real failed checkout trace, one verified patch, one runnable receipt replay, and one worker-recovery recording**. Use the observed results and their sample sizes in the README and resume.
