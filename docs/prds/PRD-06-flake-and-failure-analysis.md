# PRD-06 — Explain flakes and recurring failures

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-04. Can be built independently of PRD-05.

**User outcome.** A reviewer can tell whether a failure repeats, alternates between pass and fail under controlled conditions, or comes from the infrastructure.

1. Add a **Replay failing case** action that runs one selected browser/case five times on the same commit and profile in fresh workspaces. Show the five outcomes, timing, and trace links. Label mixed outcomes as **suspected flaky** and show the sample size.
2. Group failures by case ID, normalized assertion, and application stack location. Show the first and last observation and affected browsers, with a link to each receipt. Separate application assertions from runner or dependency failures.
3. Keep reruns linked to the original evidence. Any future change to required test policy goes through the owner-managed profile.

**Exit gate.** Use controlled fixtures to demonstrate a consistent regression, a mixed-outcome case, and a runner failure. Confirm that a successful rerun leaves the original failed attempt visible. Publish the classification results on the labeled fixtures.
