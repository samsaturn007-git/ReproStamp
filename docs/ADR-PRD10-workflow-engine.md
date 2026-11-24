# Keep PostgreSQL for durable verification jobs

The PostgreSQL queue remains the production workflow engine. A local Temporal prototype tests one alternative for crash recovery. The prototype lives under `experiments/prd10` and installs its SDK in a separate environment. [PRD-10 scope](prds/PRD-10-workflow-recovery-comparison.md) · [Run the experiment](../README.md#compare-worker-recovery)

## Method

The benchmark submits the same owner-approved checkout comparison to each engine. It freezes the commit SHAs and harness at submission and runs four browser attempts against the pinned Linux image. The control lets the first worker finish. In each crash trial the coordinator kills the first worker after it observes the first app container running, starts a replacement, and waits for the replacement's first app container. Each queue had a 10-second lease or activity heartbeat timeout and one retry. Timings come from the same host's monotonic clock. They include local polling and container startup.

## Observed on 24 November 2026

The host was macOS ARM64 with PostgreSQL 18.7, Temporal CLI 1.8.3 with server 1.31.2, and Temporal Python SDK 1.36.1. The browser was Chromium 159.0.8154.6 on Linux ARM64. There was one control and two worker-crash trials per engine.

| Scenario | Engine | Submit to first app (s) | Kill to retry app (s) | Kill to result (s) | Total (s) |
| --- | --- | ---: | ---: | ---: | ---: |
| Control | PostgreSQL | 1.175 | — | — | 9.346 |
| Control | Temporal | 1.082 | — | — | 8.423 |
| Crash 1 | PostgreSQL | 1.085 | 10.338 | 18.214 | 19.300 |
| Crash 1 | Temporal | 1.067 | 11.683 | 18.964 | 20.031 |
| Crash 2 | PostgreSQL | 1.096 | 10.779 | 18.637 | 19.733 |
| Crash 2 | Temporal | 1.073 | 12.213 | 19.699 | 20.772 |

Both engines recovered both crashes and accepted one receipt per trial. Retries used the frozen checkout. PostgreSQL recorded the expired lease, and Temporal recorded a heartbeat timeout before activity attempt two. All six receipts independently verified 13 bundled files each. Their inputs, browser build, assertion outcomes, and `VERIFIED` verdict agreed. Each engine resolved a duplicate submission to the original logical job or rejected it. The runner left zero workload containers after the benchmark. [Raw timings and receipt references](../.reprostamp/prd10-20261124-203431/report.json)

PostgreSQL reached the retry app in 10.34–10.78 seconds. Temporal reached it in 11.68–12.21 seconds with the configured 10-second heartbeat and the SDK retry policy. The sample exercises crash recovery for one job on one host. It is too small to establish a throughput or reliability advantage, and the production migration would add coordination across workflow state and user-facing evidence.

## Operational tradeoffs

PostgreSQL already stores approved inputs, leases, attempt state, and timeline events for the dashboard and GitHub. The generation fence lets the queue register the accepted receipt and its artifact records in the same transaction that finishes the run. The lease watchdog and execution lock protect the local runner while an expired generation winds down.

The Temporal workflow delegates crash detection and activity retries to the service. The prototype still uses a host-side execution lock, a subprocess watchdog, generation-specific evidence paths, and receipt verification. Temporal accepts one completed result even when an activity is attempted twice. Extending this prototype to the dashboard and GitHub would require an idempotent bridge for artifact publication, cancellation, and timeline state. [Temporal activity failure detection](https://docs.temporal.io/encyclopedia/detecting-activity-failures) · [Temporal activity idempotency](https://docs.temporal.io/activity-definition)

A production Temporal deployment would add a service, a persistence and backup plan, access controls, and workflow versioning. The experiment's loopback development server stores workflow IDs, commit SHAs, and receipt digests in its local SQLite history. The owner-managed test files, artifacts, and worker credentials stay outside those payloads. Both paths use the same container boundary and the same host filesystem. Host loss, network partitions, concurrent worker fleets, and production Temporal operations are outside this sample.
