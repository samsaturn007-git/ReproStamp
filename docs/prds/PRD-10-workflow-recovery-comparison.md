# PRD-10 — Compare workflow recovery

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-03 for durable runs. PRD-09's local exit gate was complete when this research began.

**User outcome.** See how the existing PostgreSQL queue and a local Temporal prototype recover the same approved comparison after a worker is killed.

1. Keep the prototype in an opt-in experiment. Use the existing PostgreSQL queue and worker for the baseline. Use a local Temporal development server and one activity for the prototype. Both paths run the existing comparison library and pinned Docker runner against frozen checkout commits, an independent harness, and the same Chromium-only profile.
2. Run a no-fault control and two worker-crash trials per queue. Kill each first worker while its first app container is running and start a replacement with the same inputs. Match the recovery windows and retry limits. Record submission latency, retry latency, total time, runner outcomes, and receipts. Verify one accepted completion per run and reject duplicate submission.
3. Publish the measured results and an architecture decision. Explain the two deployment footprints, crash-detection and publication tradeoffs, and what remains outside the experiment.

**Exit gate.** Both queues complete the control and recover both injected crashes with one accepted receipt per trial and no orphaned runner containers. Receipts verify offline and agree on immutable inputs, browser builds, assertion outcomes, and verdict. The core comparison, replay, and durable-run regression checks pass. The report includes raw timing and recovery evidence and the decision record.
