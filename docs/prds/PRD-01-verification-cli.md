# PRD-01 — Run the first real verification

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** Nothing. This is the greenfield starting point.

**User outcome.** Run one command and see a real checkout bug fail on the base commit, pass on the candidate commit, and retain its regression coverage in Chromium.

1. **Create the fixture and project scaffold.** Build an owned checkout app with an incorrect discount calculation, a known-good fix committed separately, and a locked Playwright test outside the application tree. Add one regression test for ordinary checkout. Provide an idempotent script that creates the fixture repo with known base and candidate SHAs.
2. **Implement the CLI.** `reprostamp compare --repo PATH --base REF --head REF --profile FILE --out DIR` accepts a local Git repository and an owner-managed profile outside it. The profile declares the expected failing test, required regressions, editable application paths, and runner image. Start with `src/**` as the editable surface. Reject changes to dependency locks, test harness files, and unsupported repository entries such as submodules and symlinks before running.
3. **Run and classify.** Execute each ref twice in fresh workspaces under the same profile. Count a baseline reproduction only for the expected assertion failure from the harness. Record engine, case ID, assertion outcome, attempt, duration, and artifact path. Write `result.json`, terminal output, and a failure trace and screenshot. Publish separate CLI exit codes for verified, failed, inconclusive, and policy-blocked outcomes.

**Exit gate.** A clean setup runs the fixture without paid services. Exercise the known-good fix, an ineffective edit, a new regression, a baseline that already passes, a failed runner startup, and a disallowed file change. Each produces the expected verdict and reason. Timeout and cleanup tests confirm the temporary workload stops and its workspace is removed.
