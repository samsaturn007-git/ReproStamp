# PRD-05 — Suggest a bounded AI repair

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-04.

**User outcome.** A maintainer can request a small patch suggestion for a reproduced functional bug, review the diff, then independently verify the commit that contains it.

1. Add a `ModelProvider` interface, a deterministic CI implementation, and one optional cloud adapter. Explicitly show and approve the context before sending it. Limit input to the issue summary, selected assertion evidence, and owner-selected application files. Keep provider credentials outside the runner.
2. Accept structured output containing an explanation and a unified diff. Permit one proposal per request, apply a configured input and output budget, and validate the diff against the base SHA and approved paths. Reject edits to acceptance tests, dependencies, workflows, and protected files. Store suggestion metadata, usage, and the reviewed diff.
3. Export the proposal as a patch. The maintainer applies or edits it, commits it, and submits the actual commit to PRD-01 or PRD-03. The Verification Receipt remains tied to what ran.

**Exit gate.** Demonstrate one reviewed patch that passes independent verification and one plausible-looking patch that fails. Cover malformed output, out-of-scope edits, exhausted budget, provider errors, and untrusted text requesting additional authority. Report real model usage separately from deterministic CI results.
