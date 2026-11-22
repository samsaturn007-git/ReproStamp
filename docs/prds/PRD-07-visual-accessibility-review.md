# PRD-07 — Review visual and accessibility changes

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-04.

**User outcome.** A maintainer can spot and review a layout or accessibility regression alongside the functional test results.

1. Capture screenshots for selected routes with a pinned browser, viewport, fonts, and seeded data. Show baseline, candidate, and pixel diff. Bind screenshot approval to the exact commit, profile, browser, and screenshot digest.
2. Add axe checks to the same selected routes. Show newly detected findings by rule, impact, and target element. Include a documented keyboard walkthrough in the pilot.
3. Add results to the receipt as advisory checks by default. A profile can explicitly make a check required. Record accepted visual baselines and approval history so reviewers can see what was accepted and by whom.

**Exit gate.** Catch a seeded layout shift and a seeded accessibility violation. Show an intentional visual change being approved and demonstrate that a later screenshot requires fresh review. Verify that advisory and required checks affect the verdict according to the selected profile.
