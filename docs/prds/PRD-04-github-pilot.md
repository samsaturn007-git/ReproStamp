# PRD-04 — Pilot with GitHub pull requests

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-03.

**User outcome.** A developer opens a PR in an approved repository and sees a BuildVerify Check linked to the evidence for the exact tested commit.

1. **Connect one pilot repository.** Register a GitHub App with read access to contents and pull requests and write access to checks. Keep installation credentials in the integration process. Validate signed webhook bodies and deduplicate delivery IDs. Handle `opened`, `reopened`, and `synchronize` for same-repo PRs on the explicit allowlist, then queue the resolved base and head pair. [GitHub webhook validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
2. **Publish and reconcile.** Map `VERIFIED` to a successful check, `FAILED` to failure, and `INCONCLUSIVE` or `POLICY_BLOCKED` to action required. Key the local check record by installation, repository, head SHA, and profile. Reconcile uncertain creation responses against GitHub before retrying. Refresh PR refs before publication and mark old evidence as superseded when the PR moves. Include a verdict summary, browser coverage, and evidence link. Leave branch protection opt-in.
3. **Operate the pilot.** Document runner setup, permissions, disconnect and recovery procedures, and how to inspect a stale or failed check. Instrument queue time, browser duration, worker recovery, and publish failures. Keep PR and branch creation in the maintainer’s existing workflow.

**Exit gate.** Use one approved developer-owned repo to demonstrate a failing check, a subsequent verified commit, and a commit change while a run is active. Test invalid signatures, duplicate deliveries, fork exclusion, and a lost response after check creation. Record actual duration and recovery results with the test environment and sample sizes.

**Release B.** BuildVerify is now usable in a real PR review workflow. This is the first portfolio release.
