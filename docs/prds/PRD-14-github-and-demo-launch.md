# PRD-14 — Connect GitHub and verify the public launch

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** [PRD-13](PRD-13-public-checkout-demo.md) and PRD-04.

**User outcome.** Anyone with the demo URL can follow a real verification from an approved GitHub pull request to the browser evidence and its downloadable receipt.

**Prerequisites.** An owner-approved demo repository and GitHub App installation, a stable HTTPS webhook endpoint, and authorization to publish the selected fixture PR and evidence.

1. Connect the signed webhook to the dedicated demo repository. Keep credentials in the operator's secret storage and bind the installation to the approved profile. Apply the existing webhook checks for signatures, installation scope, delivery deduplication, and exact commit identity.
2. Exercise a same-repository PR against an ineffective candidate and then the known fix. Record the failed and successful checks and verify that each check names the tested head SHA. Re-deliver one event and verify that it produces one logical run. Point the public demo walkthrough to the approved GitHub example and the reviewed evidence for the same SHA. Check those links from an anonymous browser.
3. Rehearse a worker restart during a controlled demo run. Verify lease recovery, a single accepted receipt, and cleanup of comparison containers. Restore a matching database and evidence backup into a separate instance and open and verify a restored receipt.
4. Rehearse the full walkthrough from a fresh desktop and mobile browser. On a separate checkout and matching Linux AMD64 runner, verify and replay the hosted receipt and compare outcomes. Save the public URL, GitHub check and receipt links, verification commands, measured timings, and recovery logs in implementation status. Document how the operator pauses guest submissions and rolls back a release.

**Exit gate.** An outside visitor can run the public sample, inspect all 12 attempts, download a verified receipt, and follow the published GitHub example to evidence for the exact tested SHA. Independent replay agrees on the assertion outcomes. Worker recovery, backup restore, the public quota, and access boundaries pass. Every public link in the walkthrough works from a signed-out session.
