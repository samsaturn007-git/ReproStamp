# PRD-09 — Extend app generation and measure it

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-08.

**User outcome.** Turn requirements for a small React, TypeScript, FastAPI, and SQLite task tracker into a runnable export, then inspect how it was planned and tested.

1. Support the existing task configuration and a bounded presentation patch for the task-list heading, empty-state text, and palette. Convert requirements into typed configuration and presentation tasks. Write patches in a disposable workspace using fixed paths and typed values. Reject unsupported app types, arbitrary file edits, and changes to locked commands and dependencies.
2. Export source, a versioned manifest with fixed commands and preview support, a license, local unit tests, and startup and rerun instructions. Use the pinned Linux runner for preview validation, Python whitespace lint and unit checks, TypeScript compilation, the build, and independent Playwright acceptance. WebContainers are optional and excluded for the Python backend.
3. Index the maintained source by file digest and symbols. Rank context by task terms and failure evidence, reuse unchanged index entries, and enforce the model byte and output token budgets. Use the existing local provider and approval boundary. Mark live output experimental and retain measured usage and executable results.
4. Run a paired benchmark on the same seeded requirements and independent expected behavior. Compare one generator call with a planner/reviewer that brackets a generator call. Record raw outcomes, attempts, input bytes, provider tokens where available, cost, elapsed time, and failure modes. Measure context selection against the full-source baseline and state the limits of scripted and live samples.

**Exit gate.** Repeated golden generation yields the same source archive. A pristine export passes the build, unit, and independent browser checks and can be revalidated from its files. Unsupported requests and protected edits are rejected before execution. The benchmark reports both arms on every selected fixture, grades behavior through executable checks, accounts for model calls, and links to raw evidence. A local live run exercises the experimental path.
