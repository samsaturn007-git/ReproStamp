# PRD-02 — Ship the browser matrix and Verification Receipt

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-01.

**User outcome.** A reviewer can see the before-and-after evidence across three browser engines, download it, check its integrity, and replay the run.

1. **Expand the runner.** Provide a three-engine profile for Chromium, Firefox, and WebKit. Keep application inputs, seed, viewport, locale, oracle, and run configuration fixed per profile. Record actual browser builds. Label unsupported or missing required cells and carry them into the verdict.
2. **Version the evidence.** Export `receipt.json`, `receipt.md`, and a bundle of approved artifacts. Include repository identity, both commit SHAs, diff and lockfile hashes, oracle and profile hashes, image digest, browser builds, seed, case outcomes, verdict reasons, and artifact paths, sizes, and hashes. Hash the JSON payload using canonical JSON and SHA-256. Present it as an integrity manifest. [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)
3. **Implement offline inspection and replay.** `bverify verify BUNDLE` validates schema, safe artifact paths, and hashes. `bverify replay BUNDLE --repo PATH --profile FILE --out DIR` starts a new run after matching the recorded inputs and links the new receipt to the original. `bverify diff-receipts LEFT RIGHT` aligns browser and case IDs, shows changed outcomes, and identifies inputs that prevent a fair comparison.

**Exit gate.** An independent developer can inspect and replay a result using the README. Offline verification detects a modified receipt, a replaced trace, or a missing artifact. Replay explains a changed oracle or unavailable pinned image. Complete a run on the first fixture and a second owned repo using documented onboarding steps.

**Release A.** You can use and demo BuildVerify from the CLI at this point.
