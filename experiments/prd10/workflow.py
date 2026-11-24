"""The Temporal workflow for one immutable checkout comparison."""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

LEASE_SECONDS = 10
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class Checkout:
    run_id: str
    base_sha: str
    head_sha: str


@dataclass(frozen=True)
class Completion:
    attempt: int
    execution_state: str
    verdict: str
    receipt_sha256: str


@workflow.defn
class VerifyCheckout:
    @workflow.run
    async def run(self, checkout: Checkout) -> Completion:
        return await workflow.execute_activity(
            "compare_checkout",
            checkout,
            result_type=Completion,
            start_to_close_timeout=timedelta(minutes=4),
            schedule_to_close_timeout=timedelta(minutes=9),
            heartbeat_timeout=timedelta(seconds=LEASE_SECONDS),
            retry_policy=RetryPolicy(maximum_attempts=MAX_ATTEMPTS),
        )
