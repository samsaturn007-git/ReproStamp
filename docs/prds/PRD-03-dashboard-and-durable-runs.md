# PRD-03 — Add the dashboard and durable run execution

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-02.

**User outcome.** Open a local dashboard, select an approved repo and profile, start a run, and inspect its matrix and traces. A work interruption is visible and recoverable.

1. **Add the control plane.** Expose `POST /api/v1/runs`, run list and detail, `GET /runs/{id}/events`, `POST /runs/{id}/cancel`, and authenticated receipt and artifact downloads under `/api/v1`. Publish OpenAPI and generate a TypeScript client. Use a local owner account with an HTTP-only session cookie and CSRF protection for writes. Bind the pilot dashboard to loopback by default. Select repo and profile by registered IDs rather than browser-supplied paths.
2. **Persist and recover.** Store runs, attempts, events, and artifact references in PostgreSQL. Claim one run at a time per worker using a lease and a monotonically increasing fencing token. Commit status and its event in the same transaction. On lease expiry, retry the frozen inputs once for an infrastructure failure. A stale worker can’t finalize a newer attempt. Durable cancellation terminates the workload and records the cancelled state.
3. **Build the review screen.** Show real progress, attempts, baseline/candidate results, traces, verdict reasons, and expiry dates. Reconnect the event stream with `Last-Event-ID` and deduplicate by sequence. Use authenticated artifact downloads, HTML-escape logs, and serve trace bundles as downloads for local viewing. Default artifact retention to 30 days and show when evidence has expired.

**Exit gate.** Create a run from the UI, disconnect and reconnect, and recover the full timeline. Kill a worker mid-run and demonstrate recovery with one final receipt. Also exercise stale completion, duplicate submission, cancellation, unauthorized downloads, expired artifacts, and migration from an empty database.
