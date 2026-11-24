# PRD-12 — Deploy the verifier on a Linux VM

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** [PRD-11](PRD-11-hosted-demo-release-baseline.md).

**User outcome.** An operator can sign in over HTTPS and use the hosted verifier to compare the approved checkout commits and download the resulting receipt.

**Prerequisites.** An approved Linux AMD64 VM, operator SSH access, and DNS access for the demo. Size the VM for one active comparison and validate capacity on the host.

1. Provide a reproducible bootstrap and upgrade path from the tagged release. Run the production Next.js dashboard, FastAPI, PostgreSQL, and one Docker-backed worker as managed services. Use a TLS reverse proxy and keep the database and application service ports private. Restrict owner sign-in and operations to private access.
2. Provision the checkout fixture, owner-managed profile, independent Playwright harness, pinned runner image, and offline dependency cache. Register the known buggy and fixed commits. Keep the workload's runner boundary and ensure only the worker can access the Docker service.
3. Configure health checks and service restarts. Document where to inspect queue and worker status, free disk space, and evidence retention. Add a backup procedure for the database and matching evidence files and document how to restore them together.
4. Run the hosted checkout comparison through the dashboard. Validate secure owner sessions and live event delivery through HTTPS, including recovery after a client reconnects. Test that an anonymous session cannot reach owner endpoints or download private evidence.

**Exit gate.** The hosted owner dashboard completes all 12 checkout attempts with the expected `VERIFIED` verdict. The receipt verifies offline. Services recover after a planned restart, the event stream resumes, and an anonymous session cannot access owner functions. The deployment and backup procedures are documented. The launch restore rehearsal is part of PRD-14.
