# PRD-11 — Prepare the hosted demo release

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-09 and PRD-10. Uses the release gates from PRD-02 and PRD-03.

**User outcome.** An operator can identify, install, and reproduce the exact revision approved for the hosted demo.

1. Review the pending PRD-09 and PRD-10 changes and commit the reviewed release work. Set up a release candidate from an immutable commit, with repository-relative installation instructions and the supported Linux AMD64, Python, Node, PostgreSQL, and Docker requirements.
2. Run the existing comparison and receipt replay gate and the durable dashboard gate in hosted CI on Linux AMD64. Provision the pinned Playwright image, owned fixtures, independent harnesses, and offline caches through the maintained setup commands. Keep the existing PRD-08 mock and PRD-09 golden gates in hosted CI.
3. Build the production dashboard and install the Python CLI and control plane from a clean checkout of that revision. Record the build commands, dependency locks, runner image digest, CI links, and any setup dependencies. The hosted demo uses the production PostgreSQL queue.
4. Tag the tested release candidate. Write a short handoff with the exact commit to deploy and the steps to identify and reinstall it.

**Exit gate.** The tagged revision has green hosted results for the browser matrix, receipt integrity and independent replay, durable dashboard recovery, and both starter gates. Its production dashboard builds and its control plane installs from a clean Linux AMD64 checkout. All reported results refer to the tagged commit.
