# BuildVerify AI — Agent-Ready PRD Pack

**Research reference date:** 22 November 2026  
**Status:** Proposed system, **not** an implementation or a repository audit.  
**Intended reader:** Codex, Claude Code, a human maintainer, or an engineering interviewer.

## Purpose
BuildVerify AI is a productized, reproducible software-engineering and quality-assurance platform. Users submit a requirement or GitHub issue; the platform plans the change, operates on a sandboxed repo branch, runs verifiable tests against real browser engines, assesses regressions, and prepares a reviewable pull request with an **evidence receipt**.

This pack targets serious full-stack/SDE/platform-role resume evidence, not maximum feature count.

## Important baseline caveat
The original Project #1 was supplied **only as a brief with a redacted GitHub URL**, not a readable source repository. We **have not inspected any code or confirmed that any feature currently exists**. The implementation agent must begin with Phase 0, inspect the actual repository, and map existing capabilities to the specifications. Never blindly overwrite a mature codebase.

## Documents: read in order
1. [`docs/MASTER_PRD.md`](docs/MASTER_PRD.md) — product requirements, priorities, success metrics, user flows, and scope.
2. [`docs/COMPETITIVE_RESEARCH.md`](docs/COMPETITIVE_RESEARCH.md) — researched open-source projects, design lessons, gaps and source links.
3. [`docs/ARCHITECTURE_CONTRACTS.md`](docs/ARCHITECTURE_CONTRACTS.md) — C4-style component view, event model, API/data contracts, permissions, state machines, and ADRs.
4. [`docs/PHASED_PRDS.md`](docs/PHASED_PRDS.md) — phase-by-phase milestones, feature stories, deliverables, acceptance criteria, tests and dependencies.
5. [`docs/TESTING_SECURITY_EVALUATION.md`](docs/TESTING_SECURITY_EVALUATION.md) — threat model, isolation requirements, security matrix, QA strategy, benchmark protocol and defensible resume metrics.
6. [`docs/TASK_BACKLOG.md`](docs/TASK_BACKLOG.md) — implementation tasks with task IDs, dependencies, priorities and review gates.
7. [`docs/PORTFOLIO_DEMO_AND_INTERVIEW.md`](docs/PORTFOLIO_DEMO_AND_INTERVIEW.md) — portfolio narrative, five demo scripts, competency evidence and interview questions.
8. [`prompts/AGENT_STARTER_PROMPTS.md`](prompts/AGENT_STARTER_PROMPTS.md) — paste-ready prompts for Codex/Claude, including an initial audit and implementation loop.
9. [`AGENTS.md`](AGENTS.md) — repo-level coding-agent working contract. Copy to the project root, adjusting only for verified repo facts.

## Recommended first use
Place these documents at the root of your own repository, or provide the ZIP to the coding agent. Paste the **Phase 0 Audit** prompt from `prompts/AGENT_STARTER_PROMPTS.md`. Require the agent to create `docs/REPO_AUDIT.md`, `docs/IMPLEMENTATION_STATUS.md`, and ADRs based on actual code. **Do not request all phases in one prompt.**

## Definition of a resume-worthy result
A deployed or reproducible demo with a clear end-to-end flow; source-controlled architecture; tests with CI; a worker-failure recovery test; cross-browser failure artifacts; a verified PR with diff and evidence; actual measured performance/quality/cost numbers; and documentation showing what the author independently designed and implemented.

## Source integrity
This pack contains research pointers, not imported code. Validate licenses, dependency versions, and any security-sensitive upstream recommendations when you implement. Credit copied/adapted code and do not claim benchmarks or capabilities until independently tested.
