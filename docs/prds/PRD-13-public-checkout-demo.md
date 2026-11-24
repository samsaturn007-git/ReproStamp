# PRD-13 — Let visitors run the checkout demo

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** [PRD-12](PRD-12-deploy-hosted-verifier.md).

**User outcome.** A visitor opens the demo without an account, sees what changed in checkout, and runs the same three-browser comparison.

1. Build a public walkthrough shown with a completed fixture run from the hosted verifier. Show the base charge of $110 with `SAVE10`, the candidate charge of $90, and the unchanged $100 checkout without a promo. Include the tested SHAs, actual browser builds, attempt matrix, and evidence for the expected baseline failure. Keep execution state, assertion outcomes, and the verification verdict visible as distinct fields.
2. Add **Run live sample** backed by the existing queue. Resolve the fixture, profile, harness, and immutable commit SHAs from server-owned configuration. The public request takes no repository, commit, command, or workload settings. Concurrent requests join one queued or running sample. Enforce a durable quota of six new public runs per UTC day, with an operator control to pause admissions. Display the latest completed sample and its timestamp when submissions are paused or the quota is reached.
3. Stream only the approved demo fields and support reconnecting to a live sample. Show pending, completed, and incomplete runs accurately. Provide public evidence via an explicit demo publication list. Review the fixture receipt and any included screenshots, traces, and logs before publication. Offer the ZIP for the exact run identified beside its link, and retain a reviewed sample independently of the routine owner-run expiry policy.
4. Make the walkthrough usable on desktop and mobile with keyboard access, clear status updates, and a short offline verification and replay guide. Keep public demo routes separate from access to the owner dashboard, generic run IDs, and private evidence.

**Exit gate.** An anonymous browser can open the walkthrough, start or join one genuine run, and watch all 12 attempts. A published sample ZIP verifies offline and matches the shown SHAs. Two simultaneous submissions produce one queued run. The quota, pause, and reconnect behavior work across a service restart. Anonymous requests cannot select workload inputs or access an unapproved run or artifact.
